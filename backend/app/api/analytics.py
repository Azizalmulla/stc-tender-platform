"""
Analytics API endpoints for STC Tender Dashboard
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, case
from datetime import datetime, timedelta
from typing import List, Dict, Any

from app.db.session import get_db
from app.models.tender import Tender

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get overall tender statistics summary"""
    now = datetime.utcnow()
    
    # Total counts
    total_tenders = db.query(func.count(Tender.id)).scalar() or 0
    
    # Active tenders (deadline in future)
    active_tenders = db.query(func.count(Tender.id)).filter(
        Tender.deadline > now
    ).scalar() or 0
    
    # Expired tenders
    expired_tenders = db.query(func.count(Tender.id)).filter(
        Tender.deadline <= now
    ).scalar() or 0
    
    # This week's new tenders
    week_ago = now - timedelta(days=7)
    new_this_week = db.query(func.count(Tender.id)).filter(
        Tender.published_at >= week_ago
    ).scalar() or 0
    
    # Deadlines this week
    week_ahead = now + timedelta(days=7)
    deadlines_this_week = db.query(func.count(Tender.id)).filter(
        Tender.deadline >= now,
        Tender.deadline <= week_ahead
    ).scalar() or 0
    
    # By category
    category_counts = db.query(
        Tender.category,
        func.count(Tender.id).label('count')
    ).group_by(Tender.category).all()
    
    categories = {cat or 'unknown': count for cat, count in category_counts}
    
    return {
        "total_tenders": total_tenders,
        "active_tenders": active_tenders,
        "expired_tenders": expired_tenders,
        "new_this_week": new_this_week,
        "deadlines_this_week": deadlines_this_week,
        "by_category": categories
    }


@router.get("/trends")
def get_trends(days: int = 30, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get tender volume trends over time"""
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)
    
    # Daily tender counts
    daily_counts = db.query(
        func.date(Tender.published_at).label('date'),
        func.count(Tender.id).label('count')
    ).filter(
        Tender.published_at >= start_date
    ).group_by(
        func.date(Tender.published_at)
    ).order_by(
        func.date(Tender.published_at)
    ).all()
    
    # Format for chart
    trend_data = [
        {"date": str(date), "count": count}
        for date, count in daily_counts
    ]
    
    # Weekly aggregation
    weekly_counts = db.query(
        func.date_trunc('week', Tender.published_at).label('week'),
        func.count(Tender.id).label('count')
    ).filter(
        Tender.published_at >= start_date
    ).group_by(
        func.date_trunc('week', Tender.published_at)
    ).order_by(
        func.date_trunc('week', Tender.published_at)
    ).all()
    
    weekly_data = [
        {"week": str(week.date()) if week else None, "count": count}
        for week, count in weekly_counts
    ]
    
    return {
        "daily": trend_data,
        "weekly": weekly_data,
        "period_days": days
    }


@router.get("/ministries")
def get_top_ministries(limit: int = 10, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Get top ministries by tender count"""
    ministry_counts = db.query(
        Tender.ministry,
        func.count(Tender.id).label('count')
    ).filter(
        Tender.ministry.isnot(None),
        Tender.ministry != ''
    ).group_by(
        Tender.ministry
    ).order_by(
        func.count(Tender.id).desc()
    ).limit(limit).all()
    
    return [
        {"ministry": ministry, "count": count, "rank": i + 1}
        for i, (ministry, count) in enumerate(ministry_counts)
    ]


@router.get("/sectors")
def get_sector_breakdown(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Get tender breakdown by AI-detected sectors"""
    # Get sectors from ai_sectors JSONB field
    # Since ai_sectors is an array, we need to unnest it
    sector_counts = db.query(
        func.unnest(Tender.ai_sectors).label('sector'),
        func.count(Tender.id).label('count')
    ).filter(
        Tender.ai_sectors.isnot(None)
    ).group_by(
        func.unnest(Tender.ai_sectors)
    ).order_by(
        func.count(Tender.id).desc()
    ).limit(10).all()
    
    return [
        {"sector": sector, "count": count}
        for sector, count in sector_counts
    ]


@router.get("/deadlines")
def get_upcoming_deadlines(days: int = 14, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Get tenders with upcoming deadlines"""
    now = datetime.utcnow()
    end_date = now + timedelta(days=days)
    
    # Group by deadline date
    deadline_counts = db.query(
        func.date(Tender.deadline).label('date'),
        func.count(Tender.id).label('count')
    ).filter(
        Tender.deadline >= now,
        Tender.deadline <= end_date
    ).group_by(
        func.date(Tender.deadline)
    ).order_by(
        func.date(Tender.deadline)
    ).all()
    
    return [
        {"date": str(date), "count": count}
        for date, count in deadline_counts
    ]


@router.get("/urgency")
def get_urgency_distribution(db: Session = Depends(get_db)) -> Dict[str, int]:
    """Get distribution of tenders by urgency (days until deadline)"""
    now = datetime.utcnow()
    
    # Categorize by urgency
    urgent = db.query(func.count(Tender.id)).filter(
        Tender.deadline >= now,
        Tender.deadline <= now + timedelta(days=3)
    ).scalar() or 0
    
    this_week = db.query(func.count(Tender.id)).filter(
        Tender.deadline > now + timedelta(days=3),
        Tender.deadline <= now + timedelta(days=7)
    ).scalar() or 0
    
    this_month = db.query(func.count(Tender.id)).filter(
        Tender.deadline > now + timedelta(days=7),
        Tender.deadline <= now + timedelta(days=30)
    ).scalar() or 0
    
    later = db.query(func.count(Tender.id)).filter(
        Tender.deadline > now + timedelta(days=30)
    ).scalar() or 0
    
    expired = db.query(func.count(Tender.id)).filter(
        Tender.deadline < now
    ).scalar() or 0
    
    return {
        "urgent_3_days": urgent,
        "this_week": this_week,
        "this_month": this_month,
        "later": later,
        "expired": expired
    }


@router.get("/categories")
def get_category_stats(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Get tender statistics by category"""
    now = datetime.utcnow()
    
    category_stats = db.query(
        Tender.category,
        func.count(Tender.id).label('total'),
        func.sum(case((Tender.deadline > now, 1), else_=0)).label('active'),
        func.sum(case((Tender.deadline <= now, 1), else_=0)).label('expired')
    ).group_by(
        Tender.category
    ).all()
    
    return [
        {
            "category": cat or "unknown",
            "total": total,
            "active": active or 0,
            "expired": expired or 0
        }
        for cat, total, active, expired in category_stats
    ]


@router.get("/relevance")
def get_relevance_distribution(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get distribution of AI relevance scores for STC"""
    # Group by relevance score ranges
    high = db.query(func.count(Tender.id)).filter(
        Tender.ai_relevance_score >= 0.7
    ).scalar() or 0
    
    medium = db.query(func.count(Tender.id)).filter(
        Tender.ai_relevance_score >= 0.4,
        Tender.ai_relevance_score < 0.7
    ).scalar() or 0
    
    low = db.query(func.count(Tender.id)).filter(
        Tender.ai_relevance_score >= 0,
        Tender.ai_relevance_score < 0.4
    ).scalar() or 0
    
    not_scored = db.query(func.count(Tender.id)).filter(
        Tender.ai_relevance_score.is_(None)
    ).scalar() or 0
    
    # Average score
    avg_score = db.query(func.avg(Tender.ai_relevance_score)).filter(
        Tender.ai_relevance_score.isnot(None)
    ).scalar() or 0
    
    return {
        "high_relevance": high,
        "medium_relevance": medium,
        "low_relevance": low,
        "not_scored": not_scored,
        "average_score": round(float(avg_score), 2) if avg_score else 0
    }
