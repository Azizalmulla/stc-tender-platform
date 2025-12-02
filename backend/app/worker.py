from celery import Celery
from celery.schedules import crontab
from sqlalchemy.orm import Session
import asyncio
import hashlib
from datetime import datetime
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.tender import Tender, TenderEmbedding
from app.scraper.capt_scraper import scrape_capt
from app.ai.openai_service import OpenAIService
from app.parser.pdf_parser import TextNormalizer


# Initialize Celery
celery_app = Celery(
    'tender_worker',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone=settings.TIMEZONE,
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max
)

# Celery beat schedule (cron jobs)
celery_app.conf.beat_schedule = {
    'scrape-daily': {
        'task': 'app.worker.scrape_and_process_tenders',
        'schedule': crontab(hour=2, minute=0),  # Run daily at 2 AM Kuwait time
    },
}


@celery_app.task(name='app.worker.scrape_and_process_tenders')
def scrape_and_process_tenders():
    """
    Main task: Scrape Kuwait Alyoum and process all tenders
    """
    print("Starting daily scrape...")
    
    # Run async scraper
    tenders = asyncio.run(scrape_capt())
    
    print(f"Scraped {len(tenders)} tender items")
    
    db = SessionLocal()
    try:
        processed_count = 0
        skipped_count = 0
        
        for tender_data in tenders:
            # Check if already exists (by hash)
            existing = db.query(Tender).filter(
                Tender.hash == tender_data['hash']
            ).first()
            
            if existing:
                skipped_count += 1
                continue
            
            # Process new tender
            process_single_tender.delay(tender_data)
            processed_count += 1
        
        print(f"Queued {processed_count} new tenders for processing, skipped {skipped_count} duplicates")
        
        return {
            "status": "success",
            "scraped": len(tenders),
            "new": processed_count,
            "duplicates": skipped_count
        }
        
    finally:
        db.close()


@celery_app.task(name='app.worker.process_single_tender')
def process_single_tender(tender_data: dict):
    """
    Process a single tender: summarize, extract fields, generate embedding
    """
    db = SessionLocal()
    ai_service = OpenAIService()
    
    try:
        # 1. Extract structured data using AI
        full_text = f"{tender_data.get('title', '')} {tender_data.get('body', '')}"
        structured_data = ai_service.extract_structured_data(full_text)
        
        # Check if tender is relevant to STC (technology/telecom)
        is_stc_relevant = structured_data.get("is_stc_relevant", True)  # Default to True if missing
        if not is_stc_relevant:
            print(f"    ⏭️  Skipping non-tech tender: {tender_data.get('title', '')[:50]}")
            return None  # Skip non-relevant tenders
        
        print(f"    ✅ Tech-relevant tender detected")
        
        # Update tender data with extracted fields
        tender_data.update({
            "ministry": structured_data.get("ministry") or tender_data.get("ministry"),
            "tender_number": structured_data.get("tender_number") or tender_data.get("tender_number"),
            "deadline": structured_data.get("deadline") or tender_data.get("deadline"),
            "document_price_kd": structured_data.get("document_price_kd") or tender_data.get("document_price_kd"),
            "expected_value": structured_data.get("expected_value"),  # Tender/contract value
            "status": structured_data.get("status") or "Released",  # Open, Awarded, Cancelled
            "sector": structured_data.get("stc_sector"),  # AI-detected STC sector
            "category": structured_data.get("category") or tender_data.get("category", "Other"),
        })
        
        # 2. Generate summary and facts
        summary = ai_service.summarize_tender(
            title=tender_data.get('title', ''),
            body=tender_data.get('body', ''),
            lang=tender_data.get('lang', 'ar')
        )
        
        tender_data.update({
            "summary_ar": summary["summary_ar"],
            "summary_en": summary["summary_en"],
            "facts_ar": summary["facts_ar"],
            "facts_en": summary["facts_en"]
        })
        
        # 3. Create tender record
        tender = Tender(**tender_data)
        db.add(tender)
        db.commit()
        db.refresh(tender)
        
        # 4. Generate and store embedding
        embedding_text = f"{tender.title} {tender.body} {tender.summary_ar} {tender.summary_en}"
        embedding_vector = ai_service.generate_embedding(embedding_text)
        
        tender_embedding = TenderEmbedding(
            tender_id=tender.id,
            embedding=embedding_vector
        )
        db.add(tender_embedding)
        db.commit()
        
        print(f"Successfully processed tender: {tender.id} - {tender.title[:50]}")
        
        return {"status": "success", "tender_id": tender.id}
        
    except Exception as e:
        db.rollback()
        print(f"Error processing tender: {e}")
        return {"status": "error", "error": str(e)}
        
    finally:
        db.close()


@celery_app.task(name='app.worker.reprocess_embeddings')
def reprocess_embeddings(batch_size: int = 100):
    """
    Reprocess embeddings for tenders that don't have them
    Useful for backfilling after initial import
    """
    db = SessionLocal()
    ai_service = OpenAIService()
    
    try:
        # Find tenders without embeddings
        tenders_without_embeddings = db.query(Tender).outerjoin(
            TenderEmbedding, Tender.id == TenderEmbedding.tender_id
        ).filter(
            TenderEmbedding.tender_id.is_(None)
        ).limit(batch_size).all()
        
        processed = 0
        
        for tender in tenders_without_embeddings:
            try:
                embedding_text = f"{tender.title} {tender.body} {tender.summary_ar} {tender.summary_en}"
                embedding_vector = ai_service.generate_embedding(embedding_text)
                
                tender_embedding = TenderEmbedding(
                    tender_id=tender.id,
                    embedding=embedding_vector
                )
                db.add(tender_embedding)
                db.commit()
                processed += 1
                
            except Exception as e:
                print(f"Error processing embedding for tender {tender.id}: {e}")
                db.rollback()
                continue
        
        return {
            "status": "success",
            "processed": processed,
            "batch_size": batch_size
        }
        
    finally:
        db.close()


@celery_app.task(name='app.worker.cleanup_old_tenders')
def cleanup_old_tenders(days_old: int = 730):
    """
    Archive or delete tenders older than specified days
    Default: 2 years (730 days)
    """
    from datetime import timedelta
    
    db = SessionLocal()
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        old_tenders = db.query(Tender).filter(
            Tender.published_at < cutoff_date
        ).all()
        
        count = len(old_tenders)
        
        # For now, just log (don't actually delete)
        # In production, might want to archive to cold storage
        print(f"Found {count} tenders older than {days_old} days")
        
        return {
            "status": "success",
            "old_tenders_count": count,
            "cutoff_date": cutoff_date.isoformat()
        }
        
    finally:
        db.close()
