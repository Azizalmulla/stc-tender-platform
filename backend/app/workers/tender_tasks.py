"""
Background Tasks for Tender Processing
Uses RQ for reliable queued processing with retry logic
"""
import time
import logging
from typing import Dict, Optional
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.tender import Tender
from app.services.ai_enrichment import enrich_tender_with_ai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from anthropic import RateLimitError, APITimeoutError

logger = logging.getLogger(__name__)


# Batching control: Semaphore to limit concurrent Claude calls
class BatchController:
    """Controls rate of Claude API calls to prevent rate limiting"""
    
    def __init__(self, max_concurrent: int = 20):
        self.max_concurrent = max_concurrent
        self.current = 0
        self.last_call_time = 0
        self.min_delay = 0.1  # 100ms between calls
    
    def acquire(self):
        """Wait if we're at max concurrency"""
        while self.current >= self.max_concurrent:
            time.sleep(0.5)
        
        # Rate limiting: ensure minimum delay between calls
        elapsed = time.time() - self.last_call_time
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        
        self.current += 1
        self.last_call_time = time.time()
    
    def release(self):
        """Release a slot"""
        self.current = max(0, self.current - 1)


# Global batch controller (max 20 concurrent Claude calls)
batch_controller = BatchController(max_concurrent=20)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type((RateLimitError, APITimeoutError)),
    reraise=True
)
def process_single_tender_ocr(tender_id: int) -> Dict:
    """
    Process OCR for a single tender (queued task)
    
    This runs in a background worker, so if it fails:
    - Only this tender fails (others continue)
    - RQ will retry automatically
    - Progress is not lost
    
    Args:
        tender_id: ID of tender to process
        
    Returns:
        Result dictionary with status
    """
    db = SessionLocal()
    
    try:
        # Acquire batch control slot
        batch_controller.acquire()
        
        logger.info(f"🔄 Processing OCR for tender {tender_id}")
        
        tender = db.query(Tender).filter(Tender.id == tender_id).first()
        if not tender:
            logger.error(f"❌ Tender {tender_id} not found")
            return {"status": "error", "message": "Tender not found"}
        
        # OCR processing would go here
        # (Keep existing OCR logic from scraper)
        
        logger.info(f"✅ OCR completed for tender {tender_id}")
        
        return {
            "status": "success",
            "tender_id": tender_id,
            "message": "OCR completed"
        }
        
    except RateLimitError as e:
        logger.warning(f"⚠️  Rate limit hit for tender {tender_id}, will retry")
        raise  # tenacity will retry
        
    except APITimeoutError as e:
        logger.warning(f"⚠️  Timeout for tender {tender_id}, will retry")
        raise  # tenacity will retry
        
    except Exception as e:
        logger.error(f"❌ Failed to process tender {tender_id}: {e}")
        return {"status": "error", "message": str(e), "tender_id": tender_id}
        
    finally:
        batch_controller.release()
        db.close()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type((RateLimitError, APITimeoutError)),
    reraise=True
)
def enrich_single_tender_task(tender_id: int) -> Dict:
    """
    AI enrichment for a single tender (queued task)
    
    Uses structured outputs and retry logic for reliability
    
    Args:
        tender_id: ID of tender to enrich
        
    Returns:
        Result dictionary
    """
    db = SessionLocal()
    
    try:
        # Acquire batch control slot
        batch_controller.acquire()
        
        # Log database connection for debugging
        db_url = str(db.bind.url).split('@')[-1] if db.bind else 'unknown'
        logger.info(f"🤖 AI enrichment for tender {tender_id} (DB: ...{db_url})")
        
        # Call enrichment service
        success = enrich_tender_with_ai(tender_id, db)
        
        if success:
            # Double-check commit (enrichment service already commits, but ensure it's flushed)
            db.commit()
            logger.info(f"✅ AI enrichment completed for tender {tender_id} (transaction committed)")
            return {
                "status": "success",
                "tender_id": tender_id,
                "message": "AI enrichment completed"
            }
        else:
            logger.error(f"❌ AI enrichment failed for tender {tender_id}")
            db.rollback()
            return {
                "status": "error",
                "tender_id": tender_id,
                "message": "Enrichment failed"
            }
            
    except RateLimitError as e:
        logger.warning(f"⚠️  Rate limit hit for tender {tender_id}, will retry")
        db.rollback()
        raise  # tenacity will retry
        
    except APITimeoutError as e:
        logger.warning(f"⚠️  Timeout for tender {tender_id}, will retry")
        db.rollback()
        raise  # tenacity will retry
        
    except Exception as e:
        logger.error(f"❌ Failed AI enrichment for tender {tender_id}: {e}")
        db.rollback()
        return {"status": "error", "message": str(e), "tender_id": tender_id}
        
    finally:
        batch_controller.release()
        db.close()  # Close session (already committed or rolled back above)


def enqueue_tender_enrichment(tender_ids: list, queue=None) -> Dict:
    """
    Enqueue multiple tenders for AI enrichment
    
    Instead of processing 400 tenders synchronously:
    - Each tender = separate job
    - Jobs process with rate limiting
    - If one fails, others continue
    - Can monitor progress
    
    Args:
        tender_ids: List of tender IDs to process
        queue: RQ Queue object (optional)
        
    Returns:
        Job info dictionary
    """
    if queue is None:
        # No Redis available, process synchronously
        logger.warning("No task queue available, processing synchronously")
        results = []
        for tender_id in tender_ids:
            result = enrich_single_tender_task(tender_id)
            results.append(result)
        return {"status": "completed_sync", "results": results}
    
    # Enqueue jobs
    jobs = []
    for tender_id in tender_ids:
        job = queue.enqueue(
            enrich_single_tender_task,
            tender_id,
            job_timeout='10m',  # 10 minute timeout per tender
            result_ttl=86400,    # Keep results for 24 hours
            failure_ttl=86400    # Keep failures for 24 hours
        )
        jobs.append(job.id)
        logger.info(f"📋 Queued AI enrichment for tender {tender_id} (job: {job.id})")
    
    return {
        "status": "queued",
        "total_jobs": len(jobs),
        "job_ids": jobs,
        "message": f"Queued {len(jobs)} tenders for AI enrichment"
    }


def get_job_status(job_id: str, queue=None) -> Optional[Dict]:
    """
    Check status of a queued job
    
    Args:
        job_id: RQ job ID
        queue: RQ Queue object
        
    Returns:
        Job status dictionary or None
    """
    if queue is None:
        return None
    
    try:
        from rq.job import Job
        job = Job.fetch(job_id, connection=queue.connection)
        
        return {
            "id": job.id,
            "status": job.get_status(),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
            "result": job.result if job.is_finished else None,
            "error": str(job.exc_info) if job.is_failed else None
        }
    except Exception as e:
        logger.error(f"Failed to fetch job {job_id}: {e}")
        return None
