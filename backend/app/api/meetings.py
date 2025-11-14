from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
from app.db.session import get_db
from app.models.tender import Tender


router = APIRouter()


class MeetingResponse(BaseModel):
    id: int
    title: Optional[str]
    ministry: Optional[str]
    tender_number: Optional[str]
    meeting_date: datetime
    meeting_location: Optional[str]
    url: str
    published_at: Optional[datetime]
    deadline: Optional[datetime]
    
    class Config:
        from_attributes = True


class MeetingsSummary(BaseModel):
    total: int
    upcoming: int
    past: int
    meetings: List[MeetingResponse]


@router.get("/", response_model=MeetingsSummary)
async def get_meetings(
    limit: int = Query(50, ge=1, le=100),
    upcoming_only: bool = Query(False),
    db: Session = Depends(get_db)
):
    """
    Get pre-tender meetings
    
    - **limit**: Maximum number of meetings to return
    - **upcoming_only**: If true, only return future meetings
    """
    now = datetime.utcnow()
    
    # Base query - tenders with meeting info
    base_query = db.query(Tender).filter(
        Tender.meeting_date.isnot(None)
    )
    
    # Count totals
    total_count = base_query.count()
    
    upcoming_count = base_query.filter(
        Tender.meeting_date >= now
    ).count()
    
    past_count = base_query.filter(
        Tender.meeting_date < now
    ).count()
    
    # Get meetings
    if upcoming_only:
        meetings_query = base_query.filter(
            Tender.meeting_date >= now
        ).order_by(Tender.meeting_date.asc())
    else:
        meetings_query = base_query.order_by(
            Tender.meeting_date.desc()
        )
    
    meetings = meetings_query.limit(limit).all()
    
    return MeetingsSummary(
        total=total_count,
        upcoming=upcoming_count,
        past=past_count,
        meetings=[
            MeetingResponse(
                id=m.id,
                title=m.title,
                ministry=m.ministry,
                tender_number=m.tender_number,
                meeting_date=m.meeting_date,
                meeting_location=m.meeting_location,
                url=m.url,
                published_at=m.published_at,
                deadline=m.deadline
            )
            for m in meetings
        ]
    )


@router.get("/upcoming", response_model=List[MeetingResponse])
async def get_upcoming_meetings(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get upcoming meetings in next N days"""
    now = datetime.utcnow()
    future_date = now + timedelta(days=days)
    
    meetings = db.query(Tender).filter(
        and_(
            Tender.meeting_date.isnot(None),
            Tender.meeting_date >= now,
            Tender.meeting_date <= future_date
        )
    ).order_by(
        Tender.meeting_date.asc()
    ).limit(limit).all()
    
    return [
        MeetingResponse(
            id=m.id,
            title=m.title,
            ministry=m.ministry,
            tender_number=m.tender_number,
            meeting_date=m.meeting_date,
            meeting_location=m.meeting_location,
            url=m.url,
            published_at=m.published_at,
            deadline=m.deadline
        )
        for m in meetings
    ]
