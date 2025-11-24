from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from pydantic import BaseModel
from app.db.session import get_db
from app.models.tender import Tender
from app.services.relevance_scorer import relevance_scorer


router = APIRouter()


class NotificationItem(BaseModel):
    id: int
    title: str
    ministry: Optional[str]
    url: str
    deadline: Optional[str]
    published_at: Optional[str]
    reason: Optional[str]  # For postponed tenders
    type: str  # 'postponed', 'new', 'deadline'
    
    # AI-powered fields
    relevance_score: Optional[str] = None  # 'very_high', 'high', 'medium', 'low'
    confidence: Optional[float] = None
    keywords: Optional[List[str]] = None
    sectors: Optional[List[str]] = None
    recommended_team: Optional[str] = None
    reasoning: Optional[str] = None
    urgency: Optional[str] = None  # 'critical', 'high', 'medium', 'low'
    days_left: Optional[int] = None
    urgency_label: Optional[str] = None
    
    class Config:
        from_attributes = True


class NotificationsSummary(BaseModel):
    postponed: int
    new: int
    deadlines: int
    items: List[NotificationItem]


def enrich_notification_with_ai(tender: Tender) -> dict:
    """
    Get pre-computed AI enrichment data from database (instant!)
    Falls back to real-time AI if not yet processed.
    """
    try:
        # Check if tender has pre-computed AI data
        if tender.ai_processed_at:
            # Use pre-computed data from database ✅ FAST!
            urgency_data = relevance_scorer.calculate_urgency(tender.deadline)
            
            return {
                "relevance_score": tender.ai_relevance_score,
                "confidence": tender.ai_confidence,
                "keywords": tender.ai_keywords or [],
                "sectors": tender.ai_sectors or [],
                "recommended_team": tender.ai_recommended_team,
                "reasoning": tender.ai_reasoning,
                "urgency": urgency_data.get("urgency"),
                "days_left": urgency_data.get("days_left"),
                "urgency_label": urgency_data.get("label")
            }
        
        # Fallback: Compute real-time (slow, but ensures we always have data)
        print(f"⚠️  Tender {tender.id} not yet AI-processed, computing now...")
        relevance_data = relevance_scorer.score_tender_relevance(
            tender_title=tender.title or "",
            tender_body=tender.body or "",
            ministry=tender.ministry
        )
        
        urgency_data = relevance_scorer.calculate_urgency(tender.deadline)
        
        return {
            "relevance_score": relevance_data.get("relevance_score"),
            "confidence": relevance_data.get("confidence"),
            "keywords": relevance_data.get("keywords", []),
            "sectors": relevance_data.get("sectors", []),
            "recommended_team": relevance_data.get("recommended_team"),
            "reasoning": relevance_data.get("reasoning"),
            "urgency": urgency_data.get("urgency"),
            "days_left": urgency_data.get("days_left"),
            "urgency_label": urgency_data.get("label")
        }
    except Exception as e:
        print(f"⚠️  AI enrichment failed for tender {tender.id}: {e}")
        return {}


@router.get("/", response_model=NotificationsSummary)
async def get_notifications(
    limit: int = 20,
    enrich_with_ai: bool = True,
    db: Session = Depends(get_db)
):
    """
    Get notifications summary and recent items
    
    Categories:
    - Postponed: Tenders with deadline changes
    - New: Tenders published in last 7 days
    - Deadlines: Tenders with deadlines in next 14 days
    
    Args:
        limit: Max number of items to return
        enrich_with_ai: Add AI-powered relevance scoring (slower but more insightful)
    """
    try:
        # Use timezone-aware datetime to prevent comparison errors
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)
        fourteen_days_ahead = now + timedelta(days=14)
        
        # Count postponed tenders
        postponed_count = db.query(Tender).filter(
            Tender.is_postponed == True
        ).count()
        
        # Count new tenders (last 7 days) - safe with null check
        new_count = db.query(Tender).filter(
            and_(
                Tender.published_at.isnot(None),
                Tender.published_at >= seven_days_ago
            )
        ).count()
        
        # Count upcoming deadlines (next 14 days)
        deadlines_count = db.query(Tender).filter(
            and_(
                Tender.deadline.isnot(None),
                Tender.deadline >= now,
                Tender.deadline <= fourteen_days_ahead
            )
        ).count()
        
        # Get recent notification items (mixed from all categories)
        items = []
        
        # Get postponed items
        postponed_items = db.query(Tender).filter(
            Tender.is_postponed == True
        ).order_by(
            Tender.published_at.desc().nullslast()
        ).limit(limit // 3).all()
        
        for tender in postponed_items:
            ai_data = enrich_notification_with_ai(tender) if enrich_with_ai else {}
            items.append(NotificationItem(
                id=tender.id,
                title=tender.title or "Untitled",
                ministry=tender.ministry,
                url=tender.url,
                deadline=tender.deadline.isoformat() if tender.deadline else None,
                published_at=tender.published_at.isoformat() if tender.published_at else None,
                reason=tender.postponement_reason,
                type='postponed',
                **ai_data
            ))
        
        # Get new items - with null check
        new_items = db.query(Tender).filter(
            and_(
                Tender.published_at.isnot(None),
                Tender.published_at >= seven_days_ago
            )
        ).order_by(
            Tender.published_at.desc().nullslast()
        ).limit(limit // 3).all()
        
        for tender in new_items:
            ai_data = enrich_notification_with_ai(tender) if enrich_with_ai else {}
            items.append(NotificationItem(
                id=tender.id,
                title=tender.title or "Untitled",
                ministry=tender.ministry,
                url=tender.url,
                deadline=tender.deadline.isoformat() if tender.deadline else None,
                published_at=tender.published_at.isoformat() if tender.published_at else None,
                reason=None,
                type='new',
                **ai_data
            ))
        
        # Get deadline items
        deadline_items = db.query(Tender).filter(
            and_(
                Tender.deadline.isnot(None),
                Tender.deadline >= now,
                Tender.deadline <= fourteen_days_ahead
            )
        ).order_by(
            Tender.deadline.asc()
        ).limit(limit // 3).all()
        
        for tender in deadline_items:
            ai_data = enrich_notification_with_ai(tender) if enrich_with_ai else {}
            items.append(NotificationItem(
                id=tender.id,
                title=tender.title or "Untitled",
                ministry=tender.ministry,
                url=tender.url,
                deadline=tender.deadline.isoformat() if tender.deadline else None,
                published_at=tender.published_at.isoformat() if tender.published_at else None,
                reason=None,
                type='deadline',
                **ai_data
            ))
        
        # Sort all items by published date (most recent first)
        items.sort(key=lambda x: x.published_at or '', reverse=True)
        
        return NotificationsSummary(
            postponed=postponed_count,
            new=new_count,
            deadlines=deadlines_count,
            items=items[:limit]
        )
    except Exception as e:
        print(f"❌ Notifications error: {e}")
        import traceback
        print(f"   Stack trace:")
        traceback.print_exc()
        
        # Try to provide partial data if possible
        try:
            # At least return the counts if items failed
            return NotificationsSummary(
                postponed=postponed_count if 'postponed_count' in locals() else 0,
                new=new_count if 'new_count' in locals() else 0,
                deadlines=deadlines_count if 'deadlines_count' in locals() else 0,
                items=[]
            )
        except:
            # Complete fallback
            return NotificationsSummary(
                postponed=0,
                new=0,
                deadlines=0,
                items=[]
            )


@router.get("/postponed", response_model=List[NotificationItem])
async def get_postponed_notifications(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get all postponed tenders"""
    tenders = db.query(Tender).filter(
        Tender.is_postponed == True
    ).order_by(
        Tender.published_at.desc().nullslast()
    ).limit(limit).all()
    
    return [
        NotificationItem(
            id=t.id,
            title=t.title or "Untitled",
            ministry=t.ministry,
            url=t.url,
            deadline=t.deadline.isoformat() if t.deadline else None,
            published_at=t.published_at.isoformat() if t.published_at else None,
            reason=t.postponement_reason,
            type='postponed'
        )
        for t in tenders
    ]


@router.get("/new", response_model=List[NotificationItem])
async def get_new_notifications(
    days: int = 7,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get new tenders from last N days"""
    # Use timezone-aware datetime to prevent comparison errors
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    tenders = db.query(Tender).filter(
        Tender.published_at >= cutoff_date
    ).order_by(
        Tender.published_at.desc().nullslast()
    ).limit(limit).all()
    
    return [
        NotificationItem(
            id=t.id,
            title=t.title or "Untitled",
            ministry=t.ministry,
            url=t.url,
            deadline=t.deadline.isoformat() if t.deadline else None,
            published_at=t.published_at.isoformat() if t.published_at else None,
            reason=None,
            type='new'
        )
        for t in tenders
    ]


@router.get("/deadlines", response_model=List[NotificationItem])
async def get_deadline_notifications(
    days: int = 14,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get tenders with deadlines in next N days"""
    # Use timezone-aware datetime to prevent comparison errors
    now = datetime.now(timezone.utc)
    future_date = now + timedelta(days=days)
    
    tenders = db.query(Tender).filter(
        and_(
            Tender.deadline.isnot(None),
            Tender.deadline >= now,
            Tender.deadline <= future_date
        )
    ).order_by(
        Tender.deadline.asc()
    ).limit(limit).all()
    
    return [
        NotificationItem(
            id=t.id,
            title=t.title or "Untitled",
            ministry=t.ministry,
            url=t.url,
            deadline=t.deadline.isoformat() if t.deadline else None,
            published_at=t.published_at.isoformat() if t.published_at else None,
            reason=None,
            type='deadline'
        )
        for t in tenders
    ]
