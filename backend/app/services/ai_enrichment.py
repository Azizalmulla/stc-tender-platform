"""
Background AI Enrichment Service
Processes tenders asynchronously with Claude AI relevance analysis
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.tender import Tender
from app.services.relevance_scorer import relevance_scorer
import logging

logger = logging.getLogger(__name__)


def enrich_tender_with_ai(tender_id: int, db: Session) -> bool:
    """
    Enrich a single tender with AI analysis and save results to database
    
    Args:
        tender_id: ID of tender to process
        db: Database session
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get tender
        tender = db.query(Tender).filter(Tender.id == tender_id).first()
        if not tender:
            logger.error(f"Tender {tender_id} not found")
            return False
        
        # Skip if already processed recently (within 7 days)
        if tender.ai_processed_at:
            age_days = (datetime.now(timezone.utc) - tender.ai_processed_at).days
            if age_days < 7:
                logger.info(f"Tender {tender_id} already processed {age_days} days ago, skipping")
                return True
        
        logger.info(f"🤖 Processing tender {tender_id} with AI...")
        
        # Get AI relevance analysis
        relevance_data = relevance_scorer.score_tender_relevance(
            tender_title=tender.title or "",
            tender_body=tender.body or "",
            ministry=tender.ministry
        )
        
        # Debug: Log the actual data structure
        logger.info(f"🔍 AI Response data: {relevance_data}")
        
        # Update tender with AI results
        tender.ai_relevance_score = relevance_data.get("relevance_score")
        tender.ai_confidence = relevance_data.get("confidence")
        tender.ai_keywords = relevance_data.get("keywords", [])
        tender.ai_sectors = relevance_data.get("sectors", [])
        tender.ai_recommended_team = relevance_data.get("recommended_team")
        tender.ai_reasoning = relevance_data.get("reasoning")
        tender.ai_processed_at = datetime.now(timezone.utc)
        
        # Debug: Verify fields were set on the object
        logger.info(f"🔧 Before commit - tender.ai_relevance_score={tender.ai_relevance_score}, tender.ai_processed_at={tender.ai_processed_at}")
        
        # Commit and verify
        db.commit()
        db.refresh(tender)  # Refresh to ensure data is persisted
        
        # Verify data was actually saved
        logger.info(f"💾 Database commit successful for tender {tender_id}")
        logger.info(f"📊 Saved data: score={tender.ai_relevance_score}, keywords={len(tender.ai_keywords or [])}, processed_at={tender.ai_processed_at}")
        
        logger.info(
            f"✅ Tender {tender_id} enriched: "
            f"{relevance_data.get('relevance_score')} relevance "
            f"({relevance_data.get('confidence', 0):.0%} confidence)"
        )
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to enrich tender {tender_id}: {e}")
        db.rollback()
        return False


def enrich_unprocessed_tenders(db: Session, limit: int = 10) -> int:
    """
    Process tenders that haven't been enriched with AI yet
    
    Args:
        db: Database session
        limit: Max number of tenders to process
        
    Returns:
        Number of tenders successfully processed
    """
    try:
        # Find unprocessed tenders (newest first)
        unprocessed = db.query(Tender).filter(
            Tender.ai_processed_at.is_(None)
        ).order_by(
            Tender.created_at.desc()
        ).limit(limit).all()
        
        if not unprocessed:
            logger.info("No unprocessed tenders found")
            return 0
        
        logger.info(f"📊 Found {len(unprocessed)} unprocessed tenders, processing...")
        
        success_count = 0
        for tender in unprocessed:
            if enrich_tender_with_ai(tender.id, db):
                success_count += 1
        
        logger.info(f"✅ Processed {success_count}/{len(unprocessed)} tenders")
        return success_count
        
    except Exception as e:
        logger.error(f"❌ Batch processing failed: {e}")
        return 0


def enrich_recent_tenders(db: Session, days: int = 7, limit: int = 50) -> int:
    """
    Re-process recent tenders (useful after scraping new tenders)
    
    Args:
        db: Database session
        days: Process tenders from last N days
        limit: Max number to process
        
    Returns:
        Number of tenders processed
    """
    try:
        from datetime import timedelta
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Get recent tenders that need processing
        recent = db.query(Tender).filter(
            Tender.created_at >= cutoff_date,
            Tender.ai_processed_at.is_(None)
        ).order_by(
            Tender.created_at.desc()
        ).limit(limit).all()
        
        if not recent:
            return 0
        
        logger.info(f"🆕 Processing {len(recent)} recent tenders from last {days} days...")
        
        success_count = 0
        for tender in recent:
            if enrich_tender_with_ai(tender.id, db):
                success_count += 1
        
        return success_count
        
    except Exception as e:
        logger.error(f"❌ Recent tender processing failed: {e}")
        return 0
