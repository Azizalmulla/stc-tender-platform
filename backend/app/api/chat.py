from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from app.db.session import get_db
from app.models.tender import Tender, TenderEmbedding
from app.ai.openai_service import OpenAIService


router = APIRouter()


class ChatRequest(BaseModel):
    question: str
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


@router.post("/ask", response_model=ChatResponse)
async def ask_question(
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    Ask a question about tenders using RAG (Retrieval Augmented Generation)
    
    Supports both Arabic and English questions.
    Returns bilingual answers with citations.
    """
    if not request.question or len(request.question.strip()) < 3:
        raise HTTPException(status_code=400, detail="Question is too short")
    
    ai_service = OpenAIService()
    
    # 1. Generate embedding for the question
    question_embedding = ai_service.generate_embedding(request.question)
    
    # 2. Retrieve relevant documents using vector similarity
    results = db.query(
        Tender,
        TenderEmbedding.embedding.cosine_distance(question_embedding).label('distance')
    ).join(
        TenderEmbedding, Tender.id == TenderEmbedding.tender_id
    ).filter(
        TenderEmbedding.embedding.cosine_distance(question_embedding) < 0.4  # High relevance threshold
    ).order_by(
        'distance'
    ).limit(request.limit).all()
    
    if not results:
        return ChatResponse(
            answer_ar="لم أجد معلومات كافية للإجابة على سؤالك. يرجى إعادة صياغة السؤال أو تقديم المزيد من التفاصيل.",
            answer_en="I couldn't find enough information to answer your question. Please rephrase or provide more details.",
            citations=[],
            confidence=0.0,
            context_count=0
        )
    
    # 3. Prepare context documents
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
    
    # 4. Generate answer using GPT with context
    answer_result = ai_service.answer_question(request.question, context_docs)
    
    # 5. Build citations from retrieved documents
    citations = [
        Citation(
            url=tender.url,
            title=tender.title or "Untitled",
            published_at=tender.published_at.isoformat() if tender.published_at else None
        )
        for tender, distance in results[:3]  # Top 3 most relevant
    ]
    
    return ChatResponse(
        answer_ar=answer_result["answer_ar"],
        answer_en=answer_result["answer_en"],
        citations=citations,
        confidence=answer_result["confidence"],
        context_count=len(context_docs)
    )


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
