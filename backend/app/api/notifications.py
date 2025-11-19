from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from pydantic import BaseModel
from app.db.session import get_db
from app.models.tender import Tender


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
    
    class Config:
        from_attributes = True


class NotificationsSummary(BaseModel):
    postponed: int
    new: int
    deadlines: int
    items: List[NotificationItem]


@router.get("/", response_model=NotificationsSummary)
async def get_notifications(
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    Get notifications summary and recent items
    
    Categories:
    - Postponed: Tenders with deadline changes
    - New: Tenders published in last 7 days
    - Deadlines: Tenders with deadlines in next 14 days
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
            items.append(NotificationItem(
                id=tender.id,
                title=tender.title or "Untitled",
                ministry=tender.ministry,
                url=tender.url,
                deadline=tender.deadline.isoformat() if tender.deadline else None,
                published_at=tender.published_at.isoformat() if tender.published_at else None,
                reason=tender.postponement_reason,
                type='postponed'
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
            items.append(NotificationItem(
                id=tender.id,
                title=tender.title or "Untitled",
                ministry=tender.ministry,
                url=tender.url,
                deadline=tender.deadline.isoformat() if tender.deadline else None,
                published_at=tender.published_at.isoformat() if tender.published_at else None,
                reason=None,
                type='new'
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
            items.append(NotificationItem(
                id=tender.id,
                title=tender.title or "Untitled",
                ministry=tender.ministry,
                url=tender.url,
                deadline=tender.deadline.isoformat() if tender.deadline else None,
                published_at=tender.published_at.isoformat() if tender.published_at else None,
                reason=None,
                type='deadline'
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
