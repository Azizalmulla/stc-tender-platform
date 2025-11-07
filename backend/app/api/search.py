from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import List, Optional
from pydantic import BaseModel
from app.db.session import get_db
from app.models.tender import Tender, TenderEmbedding
from app.ai.openai_service import OpenAIService


router = APIRouter()


class SearchResult(BaseModel):
    id: int
    url: str
    title: Optional[str]
    summary_ar: Optional[str]
    summary_en: Optional[str]
    ministry: Optional[str]
    category: Optional[str]
    published_at: Optional[str]
    deadline: Optional[str]
    score: Optional[float] = None
    
    class Config:
        from_attributes = True


@router.get("/keyword", response_model=List[SearchResult])
async def keyword_search(
    q: str = Query(..., min_length=2, description="Search query"),
    lang: Optional[str] = Query(None, description="Filter by language"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Keyword-based search across tenders
    
    Searches in: title, body, ministry, category, tender_number
    """
    # Build search query
    search_term = f"%{q}%"
    
    query = db.query(Tender).filter(
        or_(
            Tender.title.ilike(search_term),
            Tender.body.ilike(search_term),
            Tender.ministry.ilike(search_term),
            Tender.category.ilike(search_term),
            Tender.tender_number.ilike(search_term),
            Tender.summary_ar.ilike(search_term),
            Tender.summary_en.ilike(search_term)
        )
    )
    
    # Language filter
    if lang:
        query = query.filter(Tender.lang == lang)
    
    # Order by relevance (published date as proxy)
    query = query.order_by(Tender.published_at.desc())
    
    results = query.limit(limit).all()
    
    return [
        SearchResult(
            id=r.id,
            url=r.url,
            title=r.title,
            summary_ar=r.summary_ar,
            summary_en=r.summary_en,
            ministry=r.ministry,
            category=r.category,
            published_at=r.published_at.isoformat() if r.published_at else None,
            deadline=r.deadline.isoformat() if r.deadline else None,
            score=None
        )
        for r in results
    ]


@router.get("/semantic", response_model=List[SearchResult])
async def semantic_search(
    q: str = Query(..., min_length=3, description="Natural language query"),
    limit: int = Query(10, ge=1, le=50),
    threshold: float = Query(0.7, ge=0.0, le=1.0, description="Similarity threshold"),
    db: Session = Depends(get_db)
):
    """
    Semantic search using embeddings
    
    Supports natural language queries in Arabic or English
    """
    ai_service = OpenAIService()
    
    # Generate query embedding
    query_embedding = ai_service.generate_embedding(q)
    
    # Perform vector similarity search using pgvector
    results = db.query(
        Tender,
        TenderEmbedding.embedding.cosine_distance(query_embedding).label('distance')
    ).join(
        TenderEmbedding, Tender.id == TenderEmbedding.tender_id
    ).filter(
        TenderEmbedding.embedding.cosine_distance(query_embedding) < (1 - threshold)
    ).order_by(
        'distance'
    ).limit(limit).all()
    
    return [
        SearchResult(
            id=tender.id,
            url=tender.url,
            title=tender.title,
            summary_ar=tender.summary_ar,
            summary_en=tender.summary_en,
            ministry=tender.ministry,
            category=tender.category,
            published_at=tender.published_at.isoformat() if tender.published_at else None,
            deadline=tender.deadline.isoformat() if tender.deadline else None,
            score=round(1 - distance, 3)
        )
        for tender, distance in results
    ]


@router.get("/hybrid", response_model=List[SearchResult])
async def hybrid_search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Hybrid search combining keyword and semantic search
    
    Returns unified results with relevance scores
    """
    ai_service = OpenAIService()
    
    # 1. Keyword search
    search_term = f"%{q}%"
    keyword_results = db.query(Tender).filter(
        or_(
            Tender.title.ilike(search_term),
            Tender.body.ilike(search_term),
            Tender.summary_ar.ilike(search_term),
            Tender.summary_en.ilike(search_term)
        )
    ).limit(limit).all()
    
    # 2. Semantic search
    query_embedding = ai_service.generate_embedding(q)
    
    semantic_results = db.query(
        Tender,
        TenderEmbedding.embedding.cosine_distance(query_embedding).label('distance')
    ).join(
        TenderEmbedding, Tender.id == TenderEmbedding.tender_id
    ).filter(
        TenderEmbedding.embedding.cosine_distance(query_embedding) < 0.5
    ).order_by(
        'distance'
    ).limit(limit // 2).all()
    
    # Combine and deduplicate results
    combined_map = {}
    
    # Add keyword results with base score
    for tender in keyword_results:
        combined_map[tender.id] = {
            "tender": tender,
            "score": 0.7  # Base keyword match score
        }
    
    # Add/boost semantic results
    for tender, distance in semantic_results:
        semantic_score = 1 - distance
        if tender.id in combined_map:
            # Boost existing result
            combined_map[tender.id]["score"] = max(combined_map[tender.id]["score"], semantic_score)
        else:
            combined_map[tender.id] = {
                "tender": tender,
                "score": semantic_score
            }
    
    # Sort by score
    sorted_results = sorted(
        combined_map.values(),
        key=lambda x: x["score"],
        reverse=True
    )[:limit]
    
    return [
        SearchResult(
            id=item["tender"].id,
            url=item["tender"].url,
            title=item["tender"].title,
            summary_ar=item["tender"].summary_ar,
            summary_en=item["tender"].summary_en,
            ministry=item["tender"].ministry,
            category=item["tender"].category,
            published_at=item["tender"].published_at.isoformat() if item["tender"].published_at else None,
            deadline=item["tender"].deadline.isoformat() if item["tender"].deadline else None,
            score=round(item["score"], 3)
        )
        for item in sorted_results
    ]
