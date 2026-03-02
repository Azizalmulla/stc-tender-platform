"""
Cron job endpoints for scheduled tasks
"""
from fastapi import APIRouter, HTTPException, Header, BackgroundTasks
from datetime import datetime
import asyncio
import re
from typing import Optional
from urllib.parse import urlparse, parse_qs

from app.core.config import settings
from app.core.cache import cache_manager  # For clearing cached responses
from app.scraper.kuwaitalyom_scraper import KuwaitAlyomScraper
from app.db.session import SessionLocal
from app.models.tender import Tender, TenderEmbedding
from app.ai.voyage_service import voyage_service  # Voyage AI for embeddings (voyage-law-2)
from app.ai.claude_service import claude_service  # Claude Sonnet 4.6 for all AI tasks
from app.parser.pdf_parser import TextNormalizer
from app.utils.date_validator import date_validator  # Extreme date accuracy

router = APIRouter(prefix="/cron", tags=["cron"])


def run_scrape_task(days_back: int = 7):
    """
    Background task to run the scrape without blocking HTTP requests.
    Uses INCREMENTAL processing to stay within 512MB memory limit.
    Each tender is processed and saved immediately, then cleared from memory.
    
    Args:
        days_back: Number of days to scrape back (default 30)
    """
    import gc  # For memory management
    
    try:
        print(f"🤖 Starting scrape from Kuwait Al-Yawm (Official Gazette) at {datetime.now()}")
        print(f"📅 Scraping last {days_back} days")
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
                days_back=days_back,
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
        
        # Check if tender is relevant to STC (technology/telecom)
        is_stc_relevant = extracted.get('is_stc_relevant', True)  # Default to True if missing
        if not is_stc_relevant:
            print(f"    ⏭️  Skipping non-tech tender (not relevant to STC)")
            db.close()
            return None
        
        print(f"    ✅ Tech-relevant tender detected")
        
        # Get deadline FIRST (before expensive operations)
        new_deadline = extracted.get('deadline')
        if new_deadline and isinstance(new_deadline, str):
            try:
                new_deadline = datetime.fromisoformat(new_deadline.replace('Z', '+00:00'))
            except:
                new_deadline = None
        
        # Skip expired tenders (deadline has passed) - check BEFORE embedding
        if new_deadline:
            today = datetime.now()
            if new_deadline.tzinfo:
                today = datetime.now(new_deadline.tzinfo)
            if new_deadline < today:
                print(f"    ⏭️  Skipping expired tender (deadline: {new_deadline.strftime('%Y-%m-%d')})")
                db.close()
                return None
            print(f"    ✅ Active tender (deadline: {new_deadline.strftime('%Y-%m-%d')})")
        
        summary = summary_data.get('summary_ar', '') if tender_data.get('language') == 'ar' else summary_data.get('summary_en', '')
        
        # Voyage embedding (only for active tenders - saves API cost)
        embedding = voyage_service.generate_embedding(text, input_type="document")
        
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
        
        # Get ministry (strip any trailing punctuation Claude occasionally includes)
        ministry = extracted.get('ministry') or tender_data.get('ministry')
        if ministry and isinstance(ministry, str):
            ministry = ministry.strip().rstrip('",;')
        
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
        
        # Extract value and classify sectors using Claude
        try:
            import json
            extract_text = f"{tender.title or ''}\n{body_text or ''}\n{summary_data.get('summary_ar', '')}\n{summary_data.get('summary_en', '')}"
            
            if len(extract_text.strip()) >= 50:
                extract_prompt = f"""Analyze this government tender and extract:

1. **value**: The tender/project value in KD (Kuwaiti Dinar). Convert millions to full numbers. Return 0 if not mentioned.

2. **sectors**: Which STC business sectors this tender is relevant to. Choose from ONLY these options:
   - "telecom" (telecommunications, fiber, 5G, mobile networks)
   - "datacenter" (data centers, cloud, servers, hosting)
   - "callcenter" (call centers, contact centers, customer service, IVR)
   - "network" (networking, security, firewalls, routers, switches)
   - "smartcity" (smart city, IoT, sensors, automation)
   
   Return empty array [] if none match.

Return ONLY valid JSON in this exact format:
{{"value": 0, "sectors": []}}

Text:
{extract_text[:3000]}"""

                extract_response = claude_service.client.messages.create(
                    model=settings.CLAUDE_MODEL,
                    max_tokens=100,
                    messages=[{"role": "user", "content": extract_prompt}]
                )
                
                extract_text_response = extract_response.content[0].text.strip()
                start = extract_text_response.find('{')
                end = extract_text_response.rfind('}') + 1
                if start >= 0 and end > start:
                    extract_data = json.loads(extract_text_response[start:end])
                    
                    value = extract_data.get('value', 0)
                    sectors = extract_data.get('sectors', [])
                    
                    if value and value > 0:
                        tender.expected_value = float(value)
                    if sectors:
                        tender.ai_sectors = sectors
                    
                    print(f"    💰 Value: {value:,.0f} KD, Sectors: {sectors}")
        except Exception as e:
            print(f"    ⚠️ Value/sector extraction failed: {e}")
        
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


@router.post("/fresh-scrape")
async def fresh_scrape(
    background_tasks: BackgroundTasks,
    days_back: int = 14,
    clear_first: bool = True,
    authorization: Optional[str] = Header(None)
):
    """
    Fresh scrape - clears database and scrapes specified days back.
    Perfect for a clean start with only active tenders.
    
    Args:
        days_back: Number of days to scrape (default 14)
        clear_first: Whether to clear database first (default True)
    """
    # Simple auth check
    cron_secret = settings.CRON_SECRET if hasattr(settings, 'CRON_SECRET') else None
    if cron_secret and authorization != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    result = {"days_back": days_back, "clear_first": clear_first}
    
    # Clear database if requested
    if clear_first:
        try:
            db = SessionLocal()
            embedding_count = db.query(TenderEmbedding).count()
            db.query(TenderEmbedding).delete()
            tender_count = db.query(Tender).count()
            db.query(Tender).delete()
            db.commit()
            db.close()
            
            # Also clear cached responses
            cache_cleared = cache_manager.clear_all()
            
            result["cleared"] = {
                "tenders": tender_count,
                "embeddings": embedding_count,
                "cache": cache_cleared
            }
            print(f"🗑️ Cleared {tender_count} tenders, {embedding_count} embeddings, {cache_cleared} cached responses")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to clear database: {str(e)}")
    
    # Queue the scrape task with specified days_back
    background_tasks.add_task(run_scrape_task, days_back)
    
    return {
        "status": "fresh_scrape_started",
        "message": f"Scraping last {days_back} days. Check logs for progress.",
        "timestamp": datetime.now().isoformat(),
        **result
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
        
        # Also clear cached responses (prevents stale AI answers)
        cache_cleared = cache_manager.clear_all()
        
        result = {
            "status": "success",
            "deleted_tenders": tender_count,
            "deleted_embeddings": embedding_count,
            "cleared_cache": cache_cleared,
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


@router.post("/extract-tender-values")
async def extract_tender_values(authorization: Optional[str] = Header(None)):
    """
    One-time job to extract tender values AND classify sectors using Claude.
    Populates expected_value and ai_sectors fields for accurate filtering.
    """
    import json
    
    cron_secret = settings.CRON_SECRET if hasattr(settings, 'CRON_SECRET') else None
    if cron_secret and authorization != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        db = SessionLocal()
        
        # Get all tenders (re-process all for sector classification)
        tenders = db.query(Tender).all()
        
        print(f"📊 Processing {len(tenders)} tenders for value + sector extraction")
        
        if not tenders:
            db.close()
            return {"status": "success", "message": "No tenders found", "extracted": 0}
        
        extracted = 0
        
        for tender in tenders:
            try:
                # Combine text for extraction
                text = f"{tender.title or ''}\n{tender.body or ''}\n{tender.summary_ar or ''}\n{tender.summary_en or ''}"
                
                if len(text.strip()) < 50:
                    continue
                
                # Use Claude to extract value AND classify sectors
                prompt = f"""Analyze this government tender and extract:

1. **value**: The tender/project value in KD (Kuwaiti Dinar). Convert millions to full numbers. Return 0 if not mentioned.

2. **sectors**: Which STC business sectors this tender is relevant to. Choose from ONLY these options:
   - "telecom" (telecommunications, fiber, 5G, mobile networks)
   - "datacenter" (data centers, cloud, servers, hosting)
   - "callcenter" (call centers, contact centers, customer service, IVR)
   - "network" (networking, security, firewalls, routers, switches)
   - "smartcity" (smart city, IoT, sensors, automation)
   
   Return empty array [] if none match.

Return ONLY valid JSON in this exact format:
{{"value": 0, "sectors": []}}

Text:
{text[:3000]}"""

                response = claude_service.client.messages.create(
                    model=settings.CLAUDE_MODEL,
                    max_tokens=100,
                    messages=[{"role": "user", "content": prompt}]
                )
                
                response_text = response.content[0].text.strip()
                
                # Parse JSON response
                try:
                    # Find JSON in response
                    start = response_text.find('{')
                    end = response_text.rfind('}') + 1
                    if start >= 0 and end > start:
                        data = json.loads(response_text[start:end])
                        
                        value = data.get('value', 0)
                        sectors = data.get('sectors', [])
                        
                        # Update tender
                        if value and value > 0:
                            tender.expected_value = float(value)
                        
                        if sectors:
                            tender.ai_sectors = sectors
                        
                        extracted += 1
                        print(f"  ✅ Tender {tender.id}: {value:,.0f} KD, sectors: {sectors}")
                        
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"  ⚠️ Tender {tender.id}: Could not parse response: {response_text[:100]}")
                    continue
                
                if extracted % 10 == 0:
                    db.commit()
                    
            except Exception as e:
                print(f"  ⚠️ Error processing tender {tender.id}: {e}")
                continue
        
        db.commit()
        db.close()
        
        print(f"✅ Successfully processed {extracted} tenders")
        
        return {
            "status": "success",
            "message": f"Extracted values and sectors for {extracted} tenders",
            "extracted": extracted
        }
        
    except Exception as e:
        print(f"❌ Error extracting tender data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _parse_edition_page_from_url(url: str) -> tuple:
    """Extract edition_id and page_number from a Kuwait Alyom tender URL.
    
    URL format: https://kuwaitalyawm.media.gov.kw/flip/index?id=3734&no=212#tender-140201
    Returns (edition_id, page_number) or (None, None) if unparseable.
    """
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        edition_id = params.get('id', [None])[0]
        page_number = params.get('no', [None])[0]
        if edition_id and page_number:
            return str(edition_id), int(page_number)
    except Exception:
        pass
    return None, None


def run_re_enrich_task(limit: int = 50, body_threshold: int = 100):
    """
    Background task to re-enrich tenders that failed AI processing.
    
    Detects tenders with body < body_threshold chars (empty shells from
    failed Claude API calls), re-fetches their PDF pages, and runs the
    full OCR + AI pipeline to populate all fields.
    
    Args:
        limit: Max number of tenders to re-process per run
        body_threshold: Tenders with body shorter than this are considered unenriched
    """
    import gc
    import json
    from sqlalchemy import func as sql_func
    
    print(f"\n{'='*60}")
    print(f"🔄 RE-ENRICHMENT: Fixing tenders with failed AI processing")
    print(f"   Threshold: body < {body_threshold} chars")
    print(f"   Limit: {limit} tenders per run")
    print(f"{'='*60}")
    
    db = SessionLocal()
    try:
        # Find unenriched tenders: body is short AND missing ministry
        unenriched = db.query(Tender).filter(
            sql_func.length(Tender.body) < body_threshold,
            Tender.ministry.is_(None)
        ).order_by(
            Tender.created_at.desc()
        ).limit(limit).all()
        
        if not unenriched:
            print("✅ No unenriched tenders found — all good!")
            db.close()
            return {"status": "no_work", "re_enriched": 0, "failed": 0, "total_found": 0}
        
        print(f"📊 Found {len(unenriched)} unenriched tenders to re-process")
        
        # Initialize scraper and normalizer
        username = settings.KUWAIT_ALYOM_USERNAME
        password = settings.KUWAIT_ALYOM_PASSWORD
        if not username or not password:
            print("❌ Kuwait Alyom credentials not configured")
            db.close()
            return {"status": "error", "message": "Missing scraper credentials"}
        
        scraper = KuwaitAlyomScraper(username=username, password=password)
        
        # Login to get session cookies (required for Playwright flipbook access)
        if not scraper.login():
            print("❌ Failed to login to Kuwait Alyom — cannot re-enrich")
            db.close()
            return {"status": "error", "message": "Login to Kuwait Alyom failed"}
        print("✅ Logged in to Kuwait Alyom")
        
        normalizer = TextNormalizer()
        
        success_count = 0
        fail_count = 0
        
        for i, tender in enumerate(unenriched, 1):
            try:
                print(f"\n  📄 [{i}/{len(unenriched)}] Re-enriching ID={tender.id}: {tender.title}")
                
                # Step 1: Extract edition_id and page_number from URL
                edition_id, page_number = _parse_edition_page_from_url(tender.url or '')
                if not edition_id or not page_number:
                    print(f"    ❌ Cannot parse edition/page from URL: {tender.url}")
                    fail_count += 1
                    continue
                
                print(f"    📖 Edition {edition_id}, Page {page_number}")
                
                # Step 2: Re-fetch PDF page and run OCR
                ocr_result = scraper.extract_pdf_text(edition_id, page_number)
                if not ocr_result or not ocr_result.get('text') or len(ocr_result['text']) < 20:
                    print(f"    ❌ OCR failed or returned minimal text")
                    fail_count += 1
                    continue
                
                pdf_text = ocr_result['text']
                ocr_ministry = ocr_result.get('ministry')
                print(f"    ✅ OCR extracted {len(pdf_text)} chars")
                
                # Step 3: Prepare text for AI processing
                description = tender.title or ''
                full_text = f"{description}\n\n{pdf_text[:50000]}"
                body_text = pdf_text[:100000]
                
                text = f"{description}\n{full_text}"
                text = normalizer.normalize_arabic(text)
                
                # Step 4: Claude AI structured extraction + summarization
                print(f"    🧠 Claude AI processing...")
                try:
                    extracted = claude_service.extract_structured_data(text)
                    summary_data = claude_service.summarize_tender(
                        description,
                        full_text,
                        tender.lang or 'ar'
                    )
                except Exception as e:
                    print(f"    ❌ Claude failed: {e}")
                    fail_count += 1
                    continue
                
                if not extracted or not summary_data:
                    print(f"    ❌ No AI extraction returned")
                    fail_count += 1
                    continue
                
                # Step 5: Parse deadline
                new_deadline = extracted.get('deadline')
                if new_deadline and isinstance(new_deadline, str):
                    try:
                        new_deadline = datetime.fromisoformat(new_deadline.replace('Z', '+00:00'))
                    except Exception:
                        new_deadline = None
                
                # Date validation
                date_validation_result = date_validator.validate_deadline(
                    new_deadline,
                    tender.published_at
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
                            except Exception:
                                pass
                
                # Step 6: Get ministry
                ministry = extracted.get('ministry') or ocr_ministry
                if ministry and isinstance(ministry, str):
                    ministry = ministry.strip().rstrip('",;')
                
                # Step 7: Generate Voyage embedding
                embedding = voyage_service.generate_embedding(text, input_type="document")
                
                # Step 8: Update tender fields
                tender.body = body_text
                tender.ministry = ministry
                tender.deadline = new_deadline
                tender.summary_ar = summary_data.get('summary_ar', '') if tender.lang == 'ar' else summary_data.get('summary_ar', '')
                tender.summary_en = summary_data.get('summary_en', '')
                tender.facts_ar = summary_data.get('facts_ar', [])
                tender.facts_en = summary_data.get('facts_en', [])
                tender.tender_number = extracted.get('tender_number') or tender.tender_number
                tender.meeting_date = ocr_result.get('meeting_date') if ocr_result.get('meeting_date') else tender.meeting_date
                tender.meeting_location = ocr_result.get('meeting_location') if ocr_result.get('meeting_location') else tender.meeting_location
                
                # Step 9: Update or create embedding
                existing_embedding = db.query(TenderEmbedding).filter(
                    TenderEmbedding.tender_id == tender.id
                ).first()
                if existing_embedding:
                    existing_embedding.embedding = embedding
                else:
                    db.add(TenderEmbedding(tender_id=tender.id, embedding=embedding))
                
                # Step 10: Extract value + sectors with Claude
                try:
                    extract_text = f"{tender.title or ''}\n{body_text or ''}\n{summary_data.get('summary_ar', '')}\n{summary_data.get('summary_en', '')}"
                    if len(extract_text.strip()) >= 50:
                        extract_prompt = f"""Analyze this government tender and extract:

1. **value**: The tender/project value in KD (Kuwaiti Dinar). Convert millions to full numbers. Return 0 if not mentioned.

2. **sectors**: Which STC business sectors this tender is relevant to. Choose from ONLY these options:
   - "telecom" (telecommunications, fiber, 5G, mobile networks)
   - "datacenter" (data centers, cloud, servers, hosting)
   - "callcenter" (call centers, contact centers, customer service, IVR)
   - "network" (networking, security, firewalls, routers, switches)
   - "smartcity" (smart city, IoT, sensors, automation)
   
   Return empty array [] if none match.

Return ONLY valid JSON in this exact format:
{{"value": 0, "sectors": []}}

Text:
{extract_text[:3000]}"""
                        
                        extract_response = claude_service.client.messages.create(
                            model=settings.CLAUDE_MODEL,
                            max_tokens=100,
                            messages=[{"role": "user", "content": extract_prompt}]
                        )
                        extract_text_response = extract_response.content[0].text.strip()
                        start = extract_text_response.find('{')
                        end = extract_text_response.rfind('}') + 1
                        if start >= 0 and end > start:
                            extract_data = json.loads(extract_text_response[start:end])
                            value = extract_data.get('value', 0)
                            sectors = extract_data.get('sectors', [])
                            if value and value > 0:
                                tender.expected_value = float(value)
                            if sectors:
                                tender.ai_sectors = sectors
                            print(f"    💰 Value: {value:,.0f} KD, Sectors: {sectors}")
                except Exception as e:
                    print(f"    ⚠️ Value/sector extraction failed: {e}")
                
                # Commit this tender
                db.commit()
                success_count += 1
                print(f"    ✅ Re-enriched successfully! body={len(body_text)} chars, ministry={ministry}")
                
                # Clear memory
                gc.collect()
                
            except Exception as e:
                print(f"    ❌ Error re-enriching tender {tender.id}: {e}")
                db.rollback()
                fail_count += 1
                gc.collect()
                continue
        
        db.close()
        
        result = {
            "status": "success",
            "total_found": len(unenriched),
            "re_enriched": success_count,
            "failed": fail_count,
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"\n{'='*60}")
        print(f"✅ RE-ENRICHMENT COMPLETED!")
        print(f"   Found: {len(unenriched)} unenriched tenders")
        print(f"   Success: {success_count}")
        print(f"   Failed: {fail_count}")
        print(f"{'='*60}")
        
        return result
        
    except Exception as e:
        print(f"❌ FATAL ERROR in re-enrichment: {e}")
        import traceback
        print(traceback.format_exc())
        db.close()
        raise


@router.post("/re-enrich")
async def re_enrich_tenders(
    background_tasks: BackgroundTasks,
    limit: int = 50,
    body_threshold: int = 100,
    dry_run: bool = False,
    authorization: Optional[str] = Header(None)
):
    """
    Re-enrich tenders that failed AI processing (e.g. due to Claude credit exhaustion).
    
    Detects tenders with body < body_threshold chars, re-fetches their PDF pages
    from Kuwait Alyom, and runs the full OCR + AI pipeline to populate:
    body, ministry, deadline, summaries, facts, embeddings, value, sectors.
    
    Args:
        limit: Max tenders to process per run (default 50)
        body_threshold: Tenders with body shorter than this are unenriched (default 100)
        dry_run: If True, just count unenriched tenders without processing
        authorization: Bearer token for auth
    """
    cron_secret = settings.CRON_SECRET if hasattr(settings, 'CRON_SECRET') else None
    if cron_secret and authorization != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    from sqlalchemy import func as sql_func
    
    # Count unenriched tenders
    db = SessionLocal()
    try:
        unenriched_count = db.query(Tender).filter(
            sql_func.length(Tender.body) < body_threshold,
            Tender.ministry.is_(None)
        ).count()
    finally:
        db.close()
    
    if unenriched_count == 0:
        return {
            "status": "no_work",
            "message": "No unenriched tenders found — all tenders are fully processed",
            "unenriched_count": 0
        }
    
    if dry_run:
        return {
            "status": "dry_run",
            "message": f"Found {unenriched_count} unenriched tenders (body < {body_threshold} chars, no ministry)",
            "unenriched_count": unenriched_count,
            "would_process": min(limit, unenriched_count)
        }
    
    # Run in background
    background_tasks.add_task(run_re_enrich_task, limit=limit, body_threshold=body_threshold)
    
    return {
        "status": "started",
        "message": f"Re-enrichment started for up to {min(limit, unenriched_count)} of {unenriched_count} unenriched tenders",
        "unenriched_count": unenriched_count,
        "processing": min(limit, unenriched_count)
    }
