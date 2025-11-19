from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import uuid
from app.db.session import get_db
from app.models.tender import Tender, TenderEmbedding
from app.models.conversation import Conversation, Message
from app.ai.openai_service import OpenAIService


router = APIRouter()


# Ministry aliases for better cross-language matching
MINISTRY_ALIASES = {
    "ministry of public works": ["وزارة الأشغال العامة"],
    "mpw": ["وزارة الأشغال العامة"],
    "kuwait oil company": ["شركة نفط الكويت"],
    "koc": ["شركة نفط الكويت"],
    "kuwait petroleum corporation": ["مؤسسة البترول الكويتية"],
    "kpc": ["مؤسسة البترول الكويتية"],
    "petrochemical industries company": ["شركة صناعة الكيماويات البترولية"],
    "pic": ["شركة صناعة الكيماويات البترولية"],
    "ministry of interior": ["وزارة الداخلية"],
    "ministry of health": ["وزارة الصحة"],
    "ministry of education": ["وزارة التربية"],
}


class ConversationMessage(BaseModel):
    role: str  # 'user' or 'assistant'
    content: str

class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None  # Session ID for conversation persistence
    lang: Optional[str] = None  # 'ar' or 'en', auto-detect if None
    limit: int = 10  # Number of context documents to use (increased for better coverage)


class Citation(BaseModel):
    url: str
    title: str
    published_at: Optional[str]


class ChatResponse(BaseModel):
    answer_ar: str
    answer_en: str
    citations: List[Citation]
    confidence: float
    context_count: int
    session_id: str  # Return session ID to frontend


@router.post("/ask", response_model=ChatResponse)
async def ask_question(
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    Ask a question about tenders using RAG with persistent conversation history
    
    Supports both Arabic and English questions.
    Returns bilingual answers with citations.
    Automatically creates and manages conversation sessions.
    """
    if not request.question or len(request.question.strip()) < 3:
        raise HTTPException(status_code=400, detail="Question is too short")
    
    # Query validation: Check if question is tender-related
    tender_keywords = [
        'tender', 'تناقص', 'مناقصة', 'مزايدة', 'ممارسة', 'deadline', 'موعد',
        'ministry', 'وزارة', 'rfq', 'rfp', 'bid', 'auction', 'contract', 'عقد',
        'procurement', 'شراء', 'koc', 'kpc', 'مؤسسة', 'شركة', 'closing', 'تنتهي'
    ]
    
    question_lower_check = request.question.lower()
    is_tender_related = any(keyword in question_lower_check for keyword in tender_keywords)
    
    # Allow questions even if no keywords if they're short conversational follow-ups
    is_short_followup = len(request.question.strip()) < 50 and request.session_id
    
    if not is_tender_related and not is_short_followup:
        print(f"⚠️  Non-tender query detected: {request.question[:50]}...")
        answer_ar = "عذراً، أنا متخصص في الإجابة على الأسئلة المتعلقة بالمناقصات الحكومية الكويتية فقط. يرجى طرح سؤال متعلق بالمناقصات أو المزايدات أو الممارسات."
        answer_en = "Sorry, I specialize in answering questions about Kuwait government tenders only. Please ask a tender-related question."
        
        # Save rejection message
        user_message_obj = db.query(Message).filter(
            Message.conversation_id == db.query(Conversation).filter(
                Conversation.session_id == (request.session_id or str(uuid.uuid4()))
            ).first().id if request.session_id else None
        ).order_by(Message.created_at.desc()).first()
        
        # Create minimal session if needed
        if not request.session_id:
            temp_session_id = str(uuid.uuid4())
            temp_conversation = Conversation(
                session_id=temp_session_id,
                title=request.question[:100]
            )
            db.add(temp_conversation)
            db.commit()
            db.refresh(temp_conversation)
            
            temp_user_msg = Message(
                conversation_id=temp_conversation.id,
                role="user",
                content=request.question
            )
            db.add(temp_user_msg)
            
            temp_assist_msg = Message(
                conversation_id=temp_conversation.id,
                role="assistant",
                content=answer_ar if request.lang == 'ar' else answer_en
            )
            db.add(temp_assist_msg)
            db.commit()
            
            return ChatResponse(
                answer_ar=answer_ar,
                answer_en=answer_en,
                citations=[],
                confidence=0.0,
                context_count=0,
                session_id=temp_session_id
            )
        
        raise HTTPException(status_code=400, detail="Query not related to tenders")
    
    # 1. Get or create conversation session
    session_id = request.session_id
    if not session_id:
        session_id = str(uuid.uuid4())
        conversation = Conversation(
            session_id=session_id,
            title=request.question[:100]  # Use first question as title
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
    else:
        conversation = db.query(Conversation).filter(
            Conversation.session_id == session_id
        ).first()
        if not conversation:
            # Create if doesn't exist
            conversation = Conversation(
                session_id=session_id,
                title=request.question[:100]
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
    
    # 2. Save user message
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=request.question
    )
    db.add(user_message)
    db.commit()
    
    # 3. Load conversation history from database
    messages = db.query(Message).filter(
        Message.conversation_id == conversation.id
    ).order_by(Message.created_at).all()
    
    conversation_history = [
        {"role": msg.role, "content": msg.content}
        for msg in messages[:-1]  # Exclude the just-added user message
    ]
    
    ai_service = OpenAIService()
    
    # 4. Smart query routing - detect specific query patterns
    question_lower = request.question.lower()
    from datetime import datetime, timedelta
    import re
    
    # Detect tender number queries (exact match, bypass RAG)
    tender_number_pattern = r'\b(rfq|rfp|tender|مناقصة|رقم)\s*[:\-]?\s*([0-9]+[-/]*[0-9]*)\b'
    tender_match = re.search(tender_number_pattern, question_lower)
    
    if tender_match:
        tender_num = tender_match.group(2)
        print(f"🎯 Exact match query for tender: {tender_num}")
        
        # Direct database lookup by tender number
        exact_tender = db.query(Tender).filter(
            Tender.tender_number.ilike(f"%{tender_num}%")
        ).first()
        
        if exact_tender:
            print(f"✅ Found exact tender: {exact_tender.title}")
            # Return this tender directly without RAG with FULL context
            context_docs = [{
                "title": exact_tender.title or "",
                "tender_number": exact_tender.tender_number or "Not specified",
                "body": exact_tender.body or "",
                "summary_ar": exact_tender.summary_ar or "",
                "summary_en": exact_tender.summary_en or "",
                "facts_ar": exact_tender.facts_ar or [],
                "facts_en": exact_tender.facts_en or [],
                "url": exact_tender.url,
                "published_at": exact_tender.published_at.isoformat() if exact_tender.published_at else None,
                "deadline": exact_tender.deadline.isoformat() if exact_tender.deadline else None,
                "ministry": exact_tender.ministry,
                "category": exact_tender.category,
                "document_price_kd": float(exact_tender.document_price_kd) if exact_tender.document_price_kd else None,
                "meeting_date": exact_tender.meeting_date.isoformat() if exact_tender.meeting_date else None,
                "meeting_location": exact_tender.meeting_location,
                "is_postponed": exact_tender.is_postponed,
                "original_deadline": exact_tender.original_deadline.isoformat() if exact_tender.original_deadline else None,
                "postponement_reason": exact_tender.postponement_reason
            }]
            
            # Generate answer using exact match
            answer_result = ai_service.answer_question(
                request.question, 
                context_docs,
                conversation_history=conversation_history
            )
            
            # Save assistant message
            assistant_message = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=answer_result["answer_ar"] if request.lang == 'ar' else answer_result["answer_en"]
            )
            db.add(assistant_message)
            db.commit()
            
            return ChatResponse(
                answer_ar=answer_result["answer_ar"],
                answer_en=answer_result["answer_en"],
                citations=[Citation(
                    url=exact_tender.url,
                    title=exact_tender.title or "Untitled",
                    published_at=exact_tender.published_at.isoformat() if exact_tender.published_at else None
                )],
                confidence=1.0,  # Exact match = 100% confidence
                context_count=1,
                session_id=session_id
            )
    
    # Detect aggregation queries (how many, total count)
    aggregation_keywords = ['how many', 'total', 'count', 'كم عدد', 'مجموع', 'إجمالي']
    is_aggregation = any(keyword in question_lower for keyword in aggregation_keywords)
    
    if is_aggregation:
        print(f"🎯 Aggregation query detected")
        # Get total count from database instead of RAG
        total_count = db.query(Tender).count()
        
        # Apply ministry filter if detected
        ministry_filter_query = db.query(Tender)
        detected_ministries = []
        for eng_name, arabic_names in MINISTRY_ALIASES.items():
            if eng_name in question_lower:
                detected_ministries.extend(arabic_names)
        
        if detected_ministries:
            filtered_count = ministry_filter_query.filter(Tender.ministry.in_(detected_ministries)).count()
            answer_ar = f"يوجد {filtered_count} مناقصة من {', '.join(detected_ministries)} في النظام (من أصل {total_count} مناقصة إجمالية)."
            answer_en = f"There are {filtered_count} tenders from {', '.join(detected_ministries)} in the system (out of {total_count} total tenders)."
        else:
            answer_ar = f"يوجد حالياً {total_count} مناقصة في النظام."
            answer_en = f"There are currently {total_count} tenders in the system."
        
        # Save assistant message
        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer_ar if request.lang == 'ar' else answer_en
        )
        db.add(assistant_message)
        db.commit()
        
        return ChatResponse(
            answer_ar=answer_ar,
            answer_en=answer_en,
            citations=[],
            confidence=1.0,  # Direct DB query = high confidence
            context_count=0,
            session_id=session_id
        )
    
    # Base query with embedding for RAG
    question_embedding = ai_service.generate_embedding(request.question)
    base_query = db.query(
        Tender,
        TenderEmbedding.embedding.cosine_distance(question_embedding).label('distance')
    ).join(
        TenderEmbedding, Tender.id == TenderEmbedding.tender_id
    )
    
    # Apply smart filters based on query type
    
    # Ministry-based filtering: detect English ministry names and map to Arabic
    detected_ministries = []
    for eng_name, arabic_names in MINISTRY_ALIASES.items():
        if eng_name in question_lower:
            detected_ministries.extend(arabic_names)
    
    if detected_ministries:
        base_query = base_query.filter(Tender.ministry.in_(detected_ministries))
        print(f"🎯 Smart filter: Ministry in {detected_ministries}")
    
    # Deadline-related queries: filter by upcoming deadlines
    if any(keyword in question_lower for keyword in ['closing soon', 'deadline', 'ending', 'تنتهي', 'موعد', 'آخر موعد']):
        from datetime import timezone
        # Use timezone-aware datetime to prevent comparison errors
        now = datetime.now(timezone.utc)
        next_week = now + timedelta(days=7)
        base_query = base_query.filter(Tender.deadline.isnot(None), Tender.deadline <= next_week)
        print(f"🎯 Smart filter: Deadline within 7 days")
    
    # 5. Retrieve relevant documents using vector similarity
    results = base_query.filter(
        TenderEmbedding.embedding.cosine_distance(question_embedding) < 0.8  # Loose threshold based on empirical testing
    ).order_by(
        'distance'
    ).limit(request.limit).all()
    
    # Optional: Log best match distance for monitoring and quality control
    if results:
        best_distance = results[0][1]
        print(f"🔍 Top match distance: {best_distance:.3f}")
        
        # Quality control: warn if confidence is low
        if best_distance > 0.6:
            print(f"⚠️  Low confidence match (distance > 0.6)")
    
    if not results:
        answer_ar = "لم أجد معلومات كافية للإجابة على سؤالك. يرجى إعادة صياغة السؤال أو تقديم المزيد من التفاصيل."
        answer_en = "I couldn't find enough information to answer your question. Please rephrase or provide more details."
        
        # Save assistant message
        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer_ar if request.lang == 'ar' else answer_en
        )
        db.add(assistant_message)
        db.commit()
        
        return ChatResponse(
            answer_ar=answer_ar,
            answer_en=answer_en,
            citations=[],
            confidence=0.0,
            context_count=0,
            session_id=session_id
        )
    
    # 6. Prepare context documents with FULL tender information
    context_docs = [
        {
            "title": tender.title or "",
            "tender_number": tender.tender_number or "Not specified",
            "body": tender.body or "",
            "summary_ar": tender.summary_ar or "",
            "summary_en": tender.summary_en or "",
            "facts_ar": tender.facts_ar or [],
            "facts_en": tender.facts_en or [],
            "url": tender.url,
            "published_at": tender.published_at.isoformat() if tender.published_at else None,
            "deadline": tender.deadline.isoformat() if tender.deadline else None,
            "ministry": tender.ministry,
            "category": tender.category,
            "document_price_kd": float(tender.document_price_kd) if tender.document_price_kd else None,
            "meeting_date": tender.meeting_date.isoformat() if tender.meeting_date else None,
            "meeting_location": tender.meeting_location,
            "is_postponed": tender.is_postponed,
            "original_deadline": tender.original_deadline.isoformat() if tender.original_deadline else None,
            "postponement_reason": tender.postponement_reason
        }
        for tender, distance in results
    ]
    
    # 7. Generate answer using GPT with context and conversation history
    try:
        answer_result = ai_service.answer_question(
            request.question, 
            context_docs,
            conversation_history=conversation_history
        )
    except Exception as e:
        print(f"❌ Error generating answer: {e}")
        # Fallback response on AI error
        answer_result = {
            "answer_ar": "عذراً، حدث خطأ أثناء معالجة سؤالك. يرجى المحاولة مرة أخرى.",
            "answer_en": "Sorry, an error occurred while processing your question. Please try again.",
            "citations": [],
            "confidence": 0.0
        }
    
    # 8. Save assistant message
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=answer_result["answer_ar"] if request.lang == 'ar' else answer_result["answer_en"]
    )
    db.add(assistant_message)
    db.commit()
    
    # 9. Build citations from retrieved documents
    citations = [
        Citation(
            url=tender.url,
            title=tender.title or "Untitled",
            published_at=tender.published_at.isoformat() if tender.published_at else None
        )
        for tender, distance in results[:3]
    ]
    
    return ChatResponse(
        answer_ar=answer_result["answer_ar"],
        answer_en=answer_result["answer_en"],
        citations=citations,
        confidence=answer_result["confidence"],
        context_count=len(context_docs),
        session_id=session_id
    )


@router.get("/conversations/{session_id}")
async def get_conversation(
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    Get conversation history for a session
    """
    conversation = db.query(Conversation).filter(
        Conversation.session_id == session_id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    messages = db.query(Message).filter(
        Message.conversation_id == conversation.id
    ).order_by(Message.created_at).all()
    
    return {
        "session_id": conversation.session_id,
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat()
            }
            for msg in messages
        ]
    }


@router.get("/conversations")
async def list_conversations(
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    List recent conversations
    """
    conversations = db.query(Conversation).order_by(
        Conversation.updated_at.desc()
    ).limit(limit).all()
    
    return [
        {
            "session_id": conv.session_id,
            "title": conv.title,
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat(),
            "message_count": len(conv.messages)
        }
        for conv in conversations
    ]


@router.delete("/conversations/{session_id}")
async def delete_conversation(
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    Delete a conversation and all its messages
    """
    conversation = db.query(Conversation).filter(
        Conversation.session_id == session_id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    db.delete(conversation)
    db.commit()
    
    return {"status": "deleted", "session_id": session_id}


@router.post("/summarize/{tender_id}")
async def summarize_tender(
    tender_id: int,
    db: Session = Depends(get_db)
):
    """
    Generate or retrieve summary for a specific tender
    
    If summary already exists, return it. Otherwise, generate new one.
    """
    tender = db.query(Tender).filter(Tender.id == tender_id).first()
    
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
    
    # If summary already exists, return it
    if tender.summary_ar or tender.summary_en:
        return {
            "summary_ar": tender.summary_ar,
            "summary_en": tender.summary_en,
            "facts_ar": tender.facts_ar,
            "facts_en": tender.facts_en,
            "cached": True
        }
    
    # Generate new summary
    ai_service = OpenAIService()
    summary_result = ai_service.summarize_tender(
        title=tender.title or "",
        body=tender.body or "",
        lang=tender.lang or "ar"
    )
    
    # Update database
    tender.summary_ar = summary_result["summary_ar"]
    tender.summary_en = summary_result["summary_en"]
    tender.facts_ar = summary_result["facts_ar"]
    tender.facts_en = summary_result["facts_en"]
    
    db.commit()
    
    return {
        "summary_ar": summary_result["summary_ar"],
        "summary_en": summary_result["summary_en"],
        "facts_ar": summary_result["facts_ar"],
        "facts_en": summary_result["facts_en"],
        "cached": False
    }
