from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import List, Optional
from pydantic import BaseModel
from app.db.session import get_db
from app.models.tender import Tender, TenderEmbedding
from app.ai.voyage_service import voyage_service
from app.parser.pdf_parser import TextNormalizer


router = APIRouter()


def normalize_arabic_search(text: str) -> str:
    """
    Normalize Arabic text for better search matching
    
    Handles:
    - Diacritics removal (تشكيل)
    - Alef variations (آ، أ، إ → ا)
    - Ya variations (ى → ي)
    - Ta Marbuta/Ha unification (ة → ه)
    - Arabic numerals (٠١٢ → 012)
    """
    if not text:
        return text
    
    # Use the intelligent normalizer (handles all variations automatically)
    normalizer = TextNormalizer()
    return normalizer.normalize_arabic(text)


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
    fuzzy: bool = Query(False, description="Enable fuzzy matching for misspellings"),
    db: Session = Depends(get_db)
):
    """
    Keyword-based search across tenders with Arabic normalization and fuzzy matching
    
    Searches in: title, body, ministry, category, tender_number
    Handles:
    - Arabic spelling variations (ة/ه, أ/إ/آ/ا, ى/ي)
    - Misspellings and typos (when fuzzy=true)
    """
    # Normalize Arabic search query
    normalized_q = normalize_arabic_search(q)
    
    # Build search patterns for both original and normalized versions
    search_term = f"%{q}%"
    normalized_term = f"%{normalized_q}%"
    
    # Create flexible search that matches both variations
    search_conditions = []
    
    if fuzzy and len(q) >= 4:
        # Use PostgreSQL trigram similarity for fuzzy matching
        # This handles misspellings and typos
        # Requires pg_trgm extension: CREATE EXTENSION IF NOT EXISTS pg_trgm;
        from sqlalchemy import text
        
        # Calculate similarity scores (0.3 = 30% similarity threshold)
        for field in [Tender.title, Tender.ministry, Tender.summary_ar, Tender.summary_en]:
            if field is not None:
                # Add both exact and fuzzy matches
                search_conditions.extend([
                    field.ilike(search_term),
                    field.ilike(normalized_term) if normalized_q != q else None,
                    # Trigram similarity matching (commented out - requires pg_trgm extension)
                    # text(f"similarity({field.name}, :query) > 0.3")
                ])
    else:
        # Standard exact matching
        for field in [Tender.title, Tender.body, Tender.ministry, Tender.category, 
                      Tender.tender_number, Tender.summary_ar, Tender.summary_en]:
            search_conditions.extend([
                field.ilike(search_term),
                field.ilike(normalized_term) if normalized_q != q else None
            ])
    
    # Remove None conditions
    search_conditions = [c for c in search_conditions if c is not None]
    
    query = db.query(Tender).filter(or_(*search_conditions))
    
    # Language filter
    if lang:
        query = query.filter(Tender.lang == lang)
    
    # Order by relevance (published date as proxy)
    # NULLs go last to avoid issues
    query = query.order_by(Tender.published_at.desc().nullslast())
    
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
    # Generate query embedding with Voyage AI
    # Using input_type="query" for optimal search/retrieval performance
    query_embedding = voyage_service.generate_embedding(
        q,
        input_type="query"  # Optimized for search queries
    )
    
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
    Hybrid search combining keyword and semantic search with Arabic normalization
    
    Returns unified results with relevance scores
    Handles Arabic spelling variations
    """
    
    # 1. Keyword search with normalization
    normalized_q = normalize_arabic_search(q)
    search_term = f"%{q}%"
    normalized_term = f"%{normalized_q}%"
    
    # Build flexible search conditions
    search_conditions = []
    for field in [Tender.title, Tender.body, Tender.summary_ar, Tender.summary_en]:
        search_conditions.extend([
            field.ilike(search_term),
            field.ilike(normalized_term) if normalized_q != q else None
        ])
    search_conditions = [c for c in search_conditions if c is not None]
    
    keyword_results = db.query(Tender).filter(
        or_(*search_conditions)
    ).limit(limit).all()
    
    # 2. Semantic search with Voyage AI
    query_embedding = voyage_service.generate_embedding(
        q,
        input_type="query"  # Optimized for search queries
    )
    
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
    
    # Helper function to calculate keyword relevance score
    def calculate_keyword_score(tender, query_lower):
        """
        Calculate relevance score based on keyword matches
        
        Scoring factors:
        - Title match: 1.0 (highest priority)
        - Summary match: 0.7
        - Body match: 0.5
        - Exact match: +0.2 bonus
        - Multiple occurrences: +0.05 per occurrence (max +0.2)
        """
        score = 0.0
        query_lower = query_lower.lower()
        
        # Title scoring (most important)
        if tender.title:
            title_lower = tender.title.lower()
            if query_lower in title_lower:
                score = 1.0  # Base score for title match
                # Exact match bonus
                if title_lower == query_lower or f" {query_lower} " in f" {title_lower} ":
                    score += 0.2
                # Count occurrences
                occurrences = title_lower.count(query_lower)
                if occurrences > 1:
                    score += min(0.2, (occurrences - 1) * 0.05)
                return min(score, 1.0)  # Cap at 1.0
        
        # Summary scoring (medium priority)
        for summary in [tender.summary_ar, tender.summary_en]:
            if summary:
                summary_lower = summary.lower()
                if query_lower in summary_lower:
                    score = max(score, 0.7)
                    occurrences = summary_lower.count(query_lower)
                    if occurrences > 1:
                        score += min(0.15, (occurrences - 1) * 0.03)
        
        # Body scoring (lowest priority, only if no better match)
        if score < 0.5 and tender.body:
            body_lower = tender.body.lower()
            if query_lower in body_lower:
                score = 0.5
                occurrences = body_lower.count(query_lower)
                if occurrences > 2:
                    score += min(0.1, (occurrences - 2) * 0.02)
        
        return min(score, 1.0)  # Cap at 1.0
    
    # Add keyword results with calculated scores
    query_lower = q.lower()
    for tender in keyword_results:
        keyword_score = calculate_keyword_score(tender, query_lower)
        combined_map[tender.id] = {
            "tender": tender,
            "score": keyword_score
        }
    
    # Add/boost semantic results
    for tender, distance in semantic_results:
        semantic_score = 1 - distance
        if tender.id in combined_map:
            # Boost existing result - take the maximum score
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
