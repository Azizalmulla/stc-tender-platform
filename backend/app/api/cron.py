"""
Cron job endpoints for scheduled tasks
"""
from fastapi import APIRouter, HTTPException, Header, BackgroundTasks
from datetime import datetime
import asyncio
from typing import Optional

from app.core.config import settings
from app.scraper.kuwaitalyom_scraper import KuwaitAlyomScraper
from app.db.session import SessionLocal
from app.models.tender import Tender, TenderEmbedding
from app.ai.voyage_service import voyage_service  # Voyage AI for embeddings (voyage-law-2)
from app.ai.claude_service import claude_service  # Claude Sonnet 4.5 for all AI tasks
from app.parser.pdf_parser import TextNormalizer
from app.utils.date_validator import date_validator  # Extreme date accuracy

router = APIRouter(prefix="/cron", tags=["cron"])


def run_scrape_task():
    """
    Background task to run the scrape without blocking HTTP requests.
    Uses INCREMENTAL processing to stay within 512MB memory limit.
    Each tender is processed and saved immediately, then cleared from memory.
    """
    import gc  # For memory management
    
    try:
        print(f"🤖 Starting weekly scrape from Kuwait Al-Yawm (Official Gazette) at {datetime.now()}")
        print(f"📦 Using INCREMENTAL mode: Process → Save → Clear memory (512MB safe)")
        
        # Initialize Kuwait Alyom scraper with credentials
        username = settings.KUWAIT_ALYOM_USERNAME
        password = settings.KUWAIT_ALYOM_PASSWORD
        
        if not username or not password:
            raise HTTPException(
                status_code=500, 
                detail="Kuwait Alyom credentials not configured. Set KUWAIT_ALYOM_USERNAME and KUWAIT_ALYOM_PASSWORD"
            )
        
        scraper = KuwaitAlyomScraper(username=username, password=password)
        normalizer = TextNormalizer()
        
        # Categories to scrape
        categories = [
            ("1", "Tenders (المناقصات)"),
            ("2", "Auctions (المزايدات)"),
            ("18", "Practices (الممارسات)")
        ]
        
        # Track overall progress
        total_processed = 0
        total_skipped = 0
        total_errors = 0
        
        for category_id, category_name in categories:
            print(f"\n{'='*60}")
            print(f"📊 Processing {category_name}...")
            print(f"{'='*60}")
            
            # Step 1: Fetch listings only (fast, low memory - no OCR yet)
            raw_listings = scraper.fetch_listings_only(
                category_id=category_id,
                days_back=30,
                limit=200
            )
            
            if not raw_listings:
                print(f"  ⚠️  No listings found for {category_name}")
                continue
            
            # Step 2: Get existing hashes (fresh for each category)
            db = SessionLocal()
            try:
                existing_hashes = set(h[0] for h in db.query(Tender.hash).all() if h[0])
                print(f"  📊 {len(existing_hashes)} tenders already in database")
            finally:
                db.close()
            
            # Step 3: Process each tender INCREMENTALLY
            category_processed = 0
            category_skipped = 0
            
            for i, raw_tender in enumerate(raw_listings, 1):
                try:
                    # Calculate hash BEFORE OCR to check for duplicates
                    tender_hash = scraper.calculate_tender_hash(raw_tender)
                    
                    if tender_hash in existing_hashes:
                        print(f"  ⏭️  [{i}/{len(raw_listings)}] Skipping duplicate: {raw_tender.get('AdsTitle', '')[:50]}")
                        category_skipped += 1
                        continue
                    
                    print(f"\n  📄 [{i}/{len(raw_listings)}] Processing NEW: {raw_tender.get('AdsTitle', '')[:50]}")
                    
                    # Step 3a: OCR this ONE tender (memory-intensive, but cleared after)
                    tender_data = scraper.parse_tender(raw_tender, extract_pdf=True, category_id=category_id)
                    
                    if not tender_data:
                        print(f"    ❌ Failed to parse tender")
                        total_errors += 1
                        continue
                    
                    # Set category
                    category_map = {"1": "tenders", "2": "auctions", "18": "practices"}
                    tender_data['category'] = category_map.get(category_id, "tenders")
                    
                    # Step 3b: Save to database IMMEDIATELY
                    saved = save_tender_to_db(tender_data, normalizer)
                    
                    if saved:
                        category_processed += 1
                        existing_hashes.add(tender_hash)  # Add to set to avoid re-processing
                        print(f"    ✅ Saved tender #{saved}")
                    else:
                        print(f"    ⚠️  Failed to save tender")
                        total_errors += 1
                    
                    # Step 3c: Clear memory after each tender
                    del tender_data
                    gc.collect()
                    
                except Exception as e:
                    print(f"    ❌ Error processing tender: {e}")
                    total_errors += 1
                    gc.collect()  # Clear memory even on error
                    continue
            
            print(f"\n  ✅ {category_name}: {category_processed} new, {category_skipped} skipped")
            total_processed += category_processed
            total_skipped += category_skipped
            
            # Clear memory between categories
            gc.collect()
        
        # Summary
        result = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "processed": total_processed,
            "skipped": total_skipped,
            "errors": total_errors
        }
        
        print(f"\n{'='*60}")
        print(f"✅ SCRAPE COMPLETED!")
        print(f"   Processed: {total_processed} new tenders")
        print(f"   Skipped: {total_skipped} duplicates")
        print(f"   Errors: {total_errors}")
        print(f"{'='*60}")
        
        return result
        
    except Exception as e:
        print(f"❌ FATAL ERROR in scrape task: {e}")
        import traceback
        print(traceback.format_exc())
        raise


def save_tender_to_db(tender_data: dict, normalizer) -> int:
    """
    Save a single tender to the database with AI processing.
    Returns the tender ID if successful, None otherwise.
    """
    db = SessionLocal()
    try:
        # Get PDF text and prepare for AI
        pdf_text = tender_data.get('pdf_text', '')
        ocr_method = tender_data.get('ocr_method', 'unknown')
        description = tender_data.get('description', '')
        
        # Prepare text
        if pdf_text and len(pdf_text) > 100:
            print(f"    ✅ Using OCR text ({len(pdf_text)} chars, method={ocr_method})")
            full_text = f"{description}\n\n{pdf_text[:50000]}"
            body_text = pdf_text[:100000]
        else:
            full_text = description
            body_text = description
        
        text = f"{tender_data.get('title', '')}\n{full_text}"
        if tender_data.get('language') == 'ar':
            text = normalizer.normalize_arabic(text)
        
        # Claude AI processing
        print(f"    🧠 Claude AI processing...")
        try:
            extracted = claude_service.extract_structured_data(text)
            summary_data = claude_service.summarize_tender(
                tender_data.get('title', ''),
                full_text,
                tender_data.get('language', 'ar')
            )
        except Exception as e:
            print(f"    ❌ Claude failed: {e}")
            db.close()
            return None
        
        if not extracted or not summary_data:
            print(f"    ❌ No AI extraction")
            db.close()
            return None
        
        summary = summary_data.get('summary_ar', '') if tender_data.get('language') == 'ar' else summary_data.get('summary_en', '')
        
        # Voyage embedding
        embedding = voyage_service.generate_embedding(text, input_type="document")
        
        # Get deadline
        new_deadline = extracted.get('deadline')
        if new_deadline and isinstance(new_deadline, str):
            try:
                new_deadline = datetime.fromisoformat(new_deadline.replace('Z', '+00:00'))
            except:
                new_deadline = None
        
        # Date validation
        date_validation_result = date_validator.validate_deadline(
            new_deadline,
            tender_data.get('published_at')
        )
        if date_validation_result and not date_validation_result.get('valid'):
            for suggestion in date_validation_result.get('suggestions', []):
                if suggestion.get('confidence', 0) >= 0.80 and suggestion.get('suggested'):
                    try:
                        from datetime import timezone
                        new_deadline = datetime.fromisoformat(suggestion['suggested'])
                        if new_deadline.tzinfo is None:
                            new_deadline = new_deadline.replace(tzinfo=timezone.utc)
                        print(f"    📅 Date corrected")
                        break
                    except:
                        pass
        
        # Get ministry
        ministry = extracted.get('ministry') or tender_data.get('ministry')
        
        # Create tender
        tender = Tender(
            title=tender_data['title'],
            tender_number=tender_data.get('tender_number'),
            url=tender_data['url'],
            published_at=tender_data['published_at'],
            deadline=new_deadline,
            ministry=ministry,
            category=tender_data.get('category'),
            body=body_text,
            summary_ar=summary if tender_data.get('language') == 'ar' else summary_data.get('summary_ar', ''),
            summary_en=summary if tender_data.get('language') == 'en' else summary_data.get('summary_en', ''),
            facts_ar=summary_data.get('facts_ar', []),
            facts_en=summary_data.get('facts_en', []),
            lang=tender_data.get('language', 'ar'),
            hash=tender_data['hash'],
            meeting_date=tender_data.get('meeting_date'),
            meeting_location=tender_data.get('meeting_location'),
        )
        
        db.add(tender)
        db.flush()
        
        # Create embedding
        tender_embedding = TenderEmbedding(
            tender_id=tender.id,
            embedding=embedding
        )
        db.add(tender_embedding)
        db.commit()
        
        tender_id = tender.id
        db.close()
        return tender_id
        
    except Exception as e:
        print(f"    ❌ Save failed: {e}")
        db.rollback()
        db.close()
        return None


@router.post("/scrape-weekly")
async def scrape_weekly(
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None)
):
    """
    Weekly tender scraping job - runs every Sunday
    Protected by authorization header for security
    Returns immediately while scrape runs in background
    """
    # Simple auth check (use env var for cron secret)
    cron_secret = settings.CRON_SECRET if hasattr(settings, 'CRON_SECRET') else None
    if cron_secret and authorization != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Queue the scrape task to run in background
    background_tasks.add_task(run_scrape_task)
    
    return {
        "status": "scrape_started",
        "message": "Scraping task started in background. Check logs for progress.",
        "timestamp": datetime.now().isoformat()
    }


@router.post("/clear-database")
async def clear_database(authorization: Optional[str] = Header(None)):
    """
    Clear all tenders and embeddings from database
    USE WITH CAUTION - This deletes all data!
    """
    # Simple auth check (use env var for cron secret)
    cron_secret = settings.CRON_SECRET if hasattr(settings, 'CRON_SECRET') else None
    if cron_secret and authorization != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        db = SessionLocal()
        
        # Delete all embeddings first (foreign key constraint)
        embedding_count = db.query(TenderEmbedding).count()
        db.query(TenderEmbedding).delete()
        
        # Delete all tenders
        tender_count = db.query(Tender).count()
        db.query(Tender).delete()
        
        db.commit()
        db.close()
        
        result = {
            "status": "success",
            "deleted_tenders": tender_count,
            "deleted_embeddings": embedding_count,
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"🗑️  Database cleared: {result}")
        return result
        
    except Exception as e:
        print(f"❌ Error clearing database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check-postponements")
async def check_postponements(authorization: Optional[str] = Header(None)):
    """
    Daily postponement check - lighter than full scrape
    Only checks for deadline changes in existing tenders
    """
    cron_secret = settings.CRON_SECRET if hasattr(settings, 'CRON_SECRET') else None
    if cron_secret and authorization != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        print(f"🔍 Starting postponement check at {datetime.now()}")
        
        # Scrape closing tenders only (most likely to have changes)
        tenders = await scrape_capt()
        
        db = SessionLocal()
        postponed_count = 0
        
        for tender_data in tenders:
            existing = db.query(Tender).filter(
                Tender.tender_number == tender_data.get('tender_number')
            ).first()
            
            if existing and tender_data.get('deadline'):
                # Check if deadline changed
                # This is a simplified check - full implementation would parse the deadline
                pass
        
        db.close()
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "checked": len(tenders),
            "postponements_found": postponed_count
        }
        
    except Exception as e:
        print(f"❌ Error in postponement check: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup-capt-tenders")
async def cleanup_capt_tenders(authorization: Optional[str] = Header(None)):
    """
    One-time cleanup endpoint to remove all CAPT tenders from the database
    Protected by authorization header for security
    """
    # Simple auth check
    cron_secret = settings.CRON_SECRET if hasattr(settings, 'CRON_SECRET') else None
    if cron_secret and authorization != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        db = SessionLocal()
        
        # Count CAPT tenders before deletion
        from sqlalchemy import func
        capt_count = db.query(func.count(Tender.id)).filter(
            Tender.url.like('%capt.gov.kw%')
        ).scalar()
        
        print(f"🗑️  Found {capt_count} CAPT tenders to delete")
        
        if capt_count == 0:
            db.close()
            return {
                "status": "success",
                "message": "No CAPT tenders found",
                "deleted": 0
            }
        
        # Delete CAPT tenders
        deleted = db.query(Tender).filter(
            Tender.url.like('%capt.gov.kw%')
        ).delete(synchronize_session=False)
        
        db.commit()
        
        # Count remaining tenders
        remaining = db.query(func.count(Tender.id)).scalar()
        
        print(f"✅ Successfully deleted {deleted} CAPT tenders")
        print(f"📊 Remaining tenders in database: {remaining}")
        
        db.close()
        
        return {
            "status": "success",
            "message": f"Deleted {deleted} CAPT tenders",
            "deleted": deleted,
            "remaining": remaining
        }
        
    except Exception as e:
        print(f"❌ Error during CAPT tender cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enrich_tenders")
async def enrich_tenders_endpoint(
    background_tasks: BackgroundTasks,
    limit: int = 50,
    secret: str = None,
    use_queue: bool = True
):
    """
    Process existing tenders with AI enrichment (queued jobs)
    
    Uses Redis task queue for reliable processing:
    - Each tender = separate job
    - Automatic retries on failure
    - Rate limiting prevents Claude errors
    - Progress saved incrementally
    
    Args:
        limit: Max number of tenders to process (default: 50)
        secret: Authorization secret
        use_queue: Use task queue (recommended) or run synchronously
    """
    if secret != settings.CRON_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    from app.db.session import SessionLocal
    from app.models.tender import Tender
    from app.core.redis_config import default_queue
    from app.workers.tender_tasks import enqueue_tender_enrichment
    
    # Get unprocessed tenders
    db = SessionLocal()
    try:
        unprocessed = db.query(Tender.id).filter(
            Tender.ai_processed_at.is_(None)
        ).order_by(
            Tender.created_at.desc()
        ).limit(limit).all()
        
        tender_ids = [t.id for t in unprocessed]
        
        if not tender_ids:
            return {
                "status": "no_work",
                "message": "No unprocessed tenders found"
            }
        
        # Enqueue jobs
        if use_queue and default_queue:
            result = enqueue_tender_enrichment(tender_ids, queue=default_queue)
            return {
                "status": "queued",
                "total_tenders": len(tender_ids),
                "job_info": result,
                "message": f"Queued {len(tender_ids)} tenders for AI enrichment. Jobs will process with rate limiting."
            }
        else:
            # Fallback: synchronous processing
            def run_enrichment():
                try:
                    from app.services.ai_enrichment import enrich_unprocessed_tenders
                    count = enrich_unprocessed_tenders(db, limit=limit)
                    print(f"✅ AI enrichment complete: {count} tenders processed")
                except Exception as e:
                    print(f"❌ AI enrichment error: {e}")
                finally:
                    db.close()
            
            background_tasks.add_task(run_enrichment)
            
            return {
                "status": "processing_sync",
                "total_tenders": len(tender_ids),
                "message": f"Processing {len(tender_ids)} tenders synchronously (no task queue available)"
            }
            
    except Exception as e:
        db.close()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete-all-tenders")
async def delete_all_tenders(authorization: Optional[str] = Header(None)):
    """
    Delete all tenders from the database (for testing)
    Protected by authorization header for security
    """
    # Simple auth check
    cron_secret = settings.CRON_SECRET if hasattr(settings, 'CRON_SECRET') else None
    if cron_secret and authorization != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        db = SessionLocal()
        
        # Count all tenders before deletion
        from sqlalchemy import func
        total_count = db.query(func.count(Tender.id)).scalar()
        
        print(f"🗑️  Deleting all {total_count} tenders from database")
        
        if total_count == 0:
            db.close()
            return {
                "status": "success",
                "message": "No tenders found",
                "deleted": 0
            }
        
        # Delete all tenders
        deleted = db.query(Tender).delete(synchronize_session=False)
        
        db.commit()
        
        print(f"✅ Successfully deleted {deleted} tenders")
        
        db.close()
        
        return {
            "status": "success",
            "message": f"Deleted all {deleted} tenders",
            "deleted": deleted,
            "remaining": 0
        }
        
    except Exception as e:
        print(f"❌ Error during tender deletion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-embeddings")
async def generate_embeddings(authorization: Optional[str] = Header(None)):
    """
    Generate embeddings for all tenders that don't have them
    Protected by authorization header for security
    """
    # Simple auth check
    cron_secret = settings.CRON_SECRET if hasattr(settings, 'CRON_SECRET') else None
    if cron_secret and authorization != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        from app.db.session import SessionLocal
        from app.models.tender import TenderEmbedding
        
        db = SessionLocal()
        
        # Get all tenders without embeddings
        tenders_without_embeddings = db.query(Tender).outerjoin(
            TenderEmbedding, Tender.id == TenderEmbedding.tender_id
        ).filter(
            TenderEmbedding.tender_id.is_(None)
        ).all()
        
        print(f"📊 Found {len(tenders_without_embeddings)} tenders without embeddings")
        
        if not tenders_without_embeddings:
            db.close()
            return {
                "status": "success",
                "message": "All tenders already have embeddings",
                "generated": 0
            }
        
        generated = 0
        
        for tender in tenders_without_embeddings:
            try:
                # Generate text for embedding
                text = f"{tender.title or ''} {tender.summary_ar or ''} {tender.summary_en or ''} {tender.ministry or ''}"
                
                # Generate embedding with Voyage AI
                embedding = voyage_service.generate_embedding(
                    text,
                    input_type="document"
                )
                
                # Create embedding record
                tender_embedding = TenderEmbedding(
                    tender_id=tender.id,
                    embedding=embedding
                )
                db.add(tender_embedding)
                generated += 1
                
                if generated % 10 == 0:
                    print(f"  ✅ Generated {generated} embeddings...")
                    db.commit()
                    
            except Exception as e:
                print(f"  ⚠️  Error generating embedding for tender {tender.id}: {e}")
                continue
        
        db.commit()
        db.close()
        
        print(f"✅ Successfully generated {generated} embeddings")
        
        return {
            "status": "success",
            "message": f"Generated embeddings for {generated} tenders",
            "generated": generated
        }
        
    except Exception as e:
        print(f"❌ Error generating embeddings: {e}")
        raise HTTPException(status_code=500, detail=str(e))
