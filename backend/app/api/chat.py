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


class ConversationMessage(BaseModel):
    role: str  # 'user' or 'assistant'
    content: str

class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None  # Session ID for conversation persistence
    lang: Optional[str] = None  # 'ar' or 'en', auto-detect if None
    limit: int = 5  # Number of context documents to use


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
    
    # 4. Generate embedding for the question
    question_embedding = ai_service.generate_embedding(request.question)
    
    # 5. Retrieve relevant documents using vector similarity
    results = db.query(
        Tender,
        TenderEmbedding.embedding.cosine_distance(question_embedding).label('distance')
    ).join(
        TenderEmbedding, Tender.id == TenderEmbedding.tender_id
    ).filter(
        TenderEmbedding.embedding.cosine_distance(question_embedding) < 0.8  # Loose threshold based on empirical testing
    ).order_by(
        'distance'
    ).limit(request.limit).all()
    
    # Optional: Log best match distance for monitoring
    if results:
        print(f"🔍 Top match distance: {results[0][1]:.3f}")
    
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
    
    # 6. Prepare context documents
    context_docs = [
        {
            "title": tender.title or "",
            "body": tender.body or "",
            "url": tender.url,
            "published_at": tender.published_at.isoformat() if tender.published_at else None,
            "ministry": tender.ministry,
            "category": tender.category
        }
        for tender, distance in results
    ]
    
    # 7. Generate answer using GPT with context and conversation history
    answer_result = ai_service.answer_question(
        request.question, 
        context_docs,
        conversation_history=conversation_history
    )
    
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
