from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_, func, nullslast
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from app.db.session import get_db
from app.models.tender import Tender
from pydantic import BaseModel


router = APIRouter()


class TenderResponse(BaseModel):
    id: int
    url: str
    title: Optional[str]
    summary_ar: Optional[str]
    summary_en: Optional[str]
    ministry: Optional[str]
    category: Optional[str]
    tender_number: Optional[str]
    deadline: Optional[datetime]
    document_price_kd: Optional[float]
    published_at: Optional[datetime]
    lang: Optional[str]
    # Pre-tender meeting fields
    meeting_date: Optional[datetime]
    meeting_location: Optional[str]
    # Postponement fields
    is_postponed: Optional[bool]
    original_deadline: Optional[datetime]
    postponement_reason: Optional[str]
    # AI enrichment fields
    ai_relevance_score: Optional[str]
    ai_confidence: Optional[float]
    ai_keywords: Optional[List[str]]
    ai_sectors: Optional[List[str]]
    ai_recommended_team: Optional[str]
    ai_reasoning: Optional[str]
    ai_processed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class TenderDetailResponse(TenderResponse):
    body: Optional[str]
    facts_ar: Optional[List[str]]
    facts_en: Optional[List[str]]
    attachments: Optional[dict]
    created_at: Optional[datetime]
    
    class Config:
        from_attributes = True


@router.get("/", response_model=List[TenderResponse])
async def get_tenders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    ministry: Optional[str] = None,
    category: Optional[str] = None,
    lang: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    # NEW STC Filters
    sector: Optional[str] = None,
    status: Optional[str] = None,
    value_min: Optional[float] = None,
    value_max: Optional[float] = None,
    urgency: Optional[str] = None,  # "7_days" or "14_days"
    db: Session = Depends(get_db)
):
    """
    Get list of tenders with optional filters
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **ministry**: Filter by ministry name
    - **category**: Filter by category
    - **lang**: Filter by language ('ar', 'en')
    - **from_date**: Filter by published date (from)
    - **to_date**: Filter by published date (to)
    - **sector**: Filter by STC sector (Telecom infrastructure, Data center & cloud, etc.)
    - **status**: Filter by status (Open, Closed, Awarded, Cancelled)
    - **value_min**: Minimum tender value in KD
    - **value_max**: Maximum tender value in KD
    - **urgency**: Filter by urgency (7_days = deadline within 7 days, 14_days = within 14 days)
    """
    query = db.query(Tender)
    
    # Apply filters
    filters = []
    
    if ministry:
        filters.append(Tender.ministry.ilike(f"%{ministry}%"))
    
    if category:
        filters.append(Tender.category == category)
    
    if lang:
        filters.append(Tender.lang == lang)
    
    if from_date:
        filters.append(Tender.published_at >= from_date)
    
    if to_date:
        filters.append(Tender.published_at <= to_date)
    
    # NEW STC Filters
    if sector:
        filters.append(Tender.sector == sector)
    
    if status:
        filters.append(Tender.status == status)
    
    if value_min is not None:
        filters.append(Tender.expected_value >= value_min)
    
    if value_max is not None:
        filters.append(Tender.expected_value <= value_max)
    
    if urgency:
        now = datetime.now(timezone.utc)
        if urgency == "7_days":
            deadline_threshold = now + timedelta(days=7)
            filters.append(and_(
                Tender.deadline.isnot(None),
                Tender.deadline >= now,
                Tender.deadline <= deadline_threshold
            ))
        elif urgency == "14_days":
            deadline_threshold = now + timedelta(days=14)
            filters.append(and_(
                Tender.deadline.isnot(None),
                Tender.deadline >= now,
                Tender.deadline <= deadline_threshold
            ))
    
    if filters:
        query = query.filter(and_(*filters))
    
    # Order by published date (newest first)
    # Use nulls_last for better compatibility
    query = query.order_by(nullslast(Tender.published_at.desc()))
    
    # Pagination
    tenders = query.offset(skip).limit(limit).all()
    
    return tenders


@router.get("/{tender_id}", response_model=TenderDetailResponse)
async def get_tender_detail(
    tender_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific tender"""
    tender = db.query(Tender).filter(Tender.id == tender_id).first()
    
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
    
    return tender


@router.get("/stats/summary")
async def get_tender_stats(db: Session = Depends(get_db)):
    """Get summary statistics about tenders"""
    
    total_tenders = db.query(Tender).count()
    
    # Count by category
    categories = db.query(
        Tender.category, 
        func.count(Tender.id)
    ).group_by(Tender.category).all()
    
    # Count by ministry
    ministries = db.query(
        Tender.ministry, 
        func.count(Tender.id)
    ).filter(Tender.ministry.isnot(None)).group_by(Tender.ministry).limit(10).all()
    
    # Recent tenders (last 7 days)
    # Use timezone-aware datetime to prevent comparison errors
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_count = db.query(Tender).filter(
        Tender.published_at >= seven_days_ago
    ).count()
    
    # Upcoming deadlines
    # Use timezone-aware datetime to prevent comparison errors
    now = datetime.now(timezone.utc)
    upcoming_deadlines = db.query(Tender).filter(
        and_(
            Tender.deadline.isnot(None),
            Tender.deadline >= now
        )
    ).order_by(Tender.deadline).limit(10).all()
    
    return {
        "total_tenders": total_tenders,
        "categories": [{"name": cat, "count": count} for cat, count in categories if cat],
        "top_ministries": [{"name": min, "count": count} for min, count in ministries if min],
        "recent_7_days": recent_count,
        "upcoming_deadlines": [
            {
                "id": t.id,
                "title": t.title,
                "deadline": t.deadline,
                "ministry": t.ministry
            } 
            for t in upcoming_deadlines
        ]
    }
