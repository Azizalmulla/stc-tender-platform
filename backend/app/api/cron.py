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
    This function runs in a separate thread/process.
    """
    try:
        print(f"🤖 Starting weekly scrape from Kuwait Al-Yawm (Official Gazette) at {datetime.now()}")
        
        # Initialize Kuwait Alyom scraper with credentials
        username = settings.KUWAIT_ALYOM_USERNAME
        password = settings.KUWAIT_ALYOM_PASSWORD
        
        if not username or not password:
            raise HTTPException(
                status_code=500, 
                detail="Kuwait Alyom credentials not configured. Set KUWAIT_ALYOM_USERNAME and KUWAIT_ALYOM_PASSWORD"
            )
        
        # Scrape ALL categories from Kuwait Al-Yawm (Official Gazette)
        try:
            scraper = KuwaitAlyomScraper(username=username, password=password)
            
            # Scrape all three categories: Tenders, Auctions, Practices
            all_tenders = []
            
            categories = [
                ("1", "Tenders (المناقصات)"),
                ("2", "Auctions (المزايدات)"),
                ("18", "Practices (الممارسات)")
            ]
            
            for category_id, category_name in categories:
                print(f"📊 Scraping {category_name}...")
                category_tenders = scraper.scrape_all(
                    category_id=category_id,
                    days_back=30,           # 🏢 ENTERPRISE: 1 month historical backfill
                    limit=500,              # Get all tenders (500 is effectively unlimited for Kuwait)
                    extract_pdfs=True       # Enable Google Doc AI OCR
                )
                all_tenders.extend(category_tenders)
                print(f"✅ Found {len(category_tenders)} from {category_name}")
            
            tenders = all_tenders
            print(f"✅ Total scraped: {len(tenders)} announcements from Kuwait Al-Yawm (Official Gazette)")
        except Exception as scrape_error:
            print(f"❌ SCRAPER ERROR: {scrape_error}")
            print(f"Error type: {type(scrape_error).__name__}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Scraping failed: {str(scrape_error)}")
        
        # Process and import
        db = SessionLocal()
        normalizer = TextNormalizer()
        
        processed = 0
        skipped = 0
        postponed = 0
        
        for tender_data in tenders:
            try:
                # Check if already exists
                existing = db.query(Tender).filter(Tender.hash == tender_data['hash']).first()
                if existing:
                    skipped += 1
                    continue
                
                # Check for postponements
                existing_by_number = db.query(Tender).filter(
                    Tender.tender_number == tender_data.get('tender_number')
                ).first() if tender_data.get('tender_number') else None
                
                # Kuwait Alyom scraper already extracted PDF text via OCR
                pdf_text = tender_data.get('pdf_text')  # Already extracted by scraper
                ocr_method = tender_data.get('ocr_method', 'unknown')  # OCR source
                description = tender_data.get('description', '')
                
                # Prepare text for AI (combine description + PDF content)
                # Simple validation: Claude Vision always provides quality output
                def is_valid_body_text(text, method):
                    """Validate OCR text - Claude Vision is always trusted"""
                    if not text or len(text.strip()) < 100:
                        return False
                    
                    # Trust Claude Vision (our primary OCR)
                    if method == 'claude':
                        print(f"  ✅ Using Claude Vision OCR ({len(text)} chars)")
                        return True
                    
                    # Legacy/unknown sources: basic validation
                    text_len = len(text)
                    arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
                    english_chars = sum(1 for c in text if c.isalpha() and c.isascii())
                    content_ratio = (arabic_chars + english_chars) / text_len if text_len > 0 else 0
                    
                    if content_ratio < 0.15:
                        print(f"  ❌ {method} OCR: Low content ratio ({content_ratio:.1%})")
                        return False
                    
                    print(f"  ✅ {method} OCR validated")
                    return True
                
                if pdf_text and is_valid_body_text(pdf_text, ocr_method):
                    print(f"  ✅ Using OCR extracted text ({len(pdf_text)} characters, method={ocr_method})")
                    # Use PDF text as main body, description as summary
                    full_text = f"{description}\n\n{pdf_text[:50000]}"  # Limit to 50K chars
                    body_text = pdf_text[:100000]  # Store up to 100K chars
                elif pdf_text:
                    print(f"  ⚠️  OCR text quality check FAILED (method={ocr_method})")
                    print(f"     - Text length: {len(pdf_text)} chars")
                    print(f"     - Pipe ratio: {pdf_text.count('|') / len(pdf_text):.2%}")
                    print(f"     - Using description as fallback")
                    full_text = description
                    body_text = description
                else:
                    print(f"  ⚠️  No PDF text available, using metadata only")
                    full_text = description
                    body_text = description
                
                text = f"{tender_data.get('title', '')}\n{full_text}"
                if tender_data.get('language') == 'ar':
                    text = normalizer.normalize_arabic(text)
                
                # ============================================
                # Claude Sonnet 4.5 for ALL AI Processing
                # OCR, Extraction, Summarization - Single Model for Quality & Consistency
                # ============================================
                
                # Use Claude for summarization & extraction
                extracted = None
                summary_data = None
                
                try:
                    print(f"  🧠 Using Claude Sonnet 4.5 for summarization and extraction...")
                    
                    # Structured extraction with Claude
                    extracted = claude_service.extract_structured_data(text)
                    
                    # Pre-validate dates before summarization
                    potential_date_issue = ""
                    if extracted.get('deadline') and tender_data.get('published_at'):
                        try:
                            from datetime import datetime as dt
                            deadline_dt = dt.fromisoformat(extracted['deadline'].replace('Z', '+00:00')) if isinstance(extracted['deadline'], str) else extracted['deadline']
                            published_dt = tender_data['published_at']
                            if deadline_dt < published_dt:
                                potential_date_issue = "\n\n⚠️ تحذير: الموعد النهائي قبل تاريخ النشر - قد يكون خطأ في التاريخ أو مناقصة منتهية"
                        except:
                            pass
                    
                    # Summarization with Claude
                    summary_data = claude_service.summarize_tender(
                        tender_data.get('title', ''),
                        full_text + potential_date_issue,
                        tender_data.get('language', 'ar')
                    )
                    
                    print(f"  ✅ Claude AI processing successful")
                
                except Exception as e:
                    print(f"  ❌ Claude processing failed: {e}")
                    print(f"  ⚠️  Skipping tender due to AI processing failure")
                    extracted = None
                    summary_data = None
                
                # If Claude failed, skip this tender (no fallback)
                if not extracted or not summary_data:
                    print(f"  ⚠️  Skipping tender - no valid AI extraction available")
                    continue
                
                summary = summary_data.get('summary_ar', '') if tender_data.get('language') == 'ar' else summary_data.get('summary_en', '')
                
                # Voyage AI for embeddings (voyage-law-2 optimized for legal documents)
                embedding = voyage_service.generate_embedding(
                    text,
                    input_type="document"  # Tenders are documents being stored
                )
                
                # Check for postponement
                new_deadline = extracted.get('deadline')
                is_postponed = False
                original_deadline = None
                deadline_history = None
                postponement_reason = None
                
                # Convert new_deadline to datetime if it's a string
                if new_deadline and isinstance(new_deadline, str):
                    try:
                        new_deadline = datetime.fromisoformat(new_deadline.replace('Z', '+00:00'))
                    except:
                        new_deadline = None
                
                if existing_by_number and existing_by_number.deadline and new_deadline:
                    # Ensure both datetimes are timezone-aware for comparison
                    from datetime import timezone
                    existing_deadline = existing_by_number.deadline
                    if existing_deadline.tzinfo is None:
                        # Make existing deadline timezone-aware (UTC)
                        existing_deadline = existing_deadline.replace(tzinfo=timezone.utc)
                    
                    # Also ensure new_deadline is timezone-aware
                    if new_deadline.tzinfo is None:
                        new_deadline = new_deadline.replace(tzinfo=timezone.utc)
                    
                    if new_deadline > existing_deadline:
                        is_postponed = True
                        original_deadline = existing_by_number.original_deadline or existing_by_number.deadline
                        deadline_history = existing_by_number.deadline_history or []
                        deadline_history.append({
                            'deadline': existing_by_number.deadline.isoformat(),
                            'changed_at': datetime.now().isoformat(),
                            'reason': 'Deadline extended'
                        })
                        postponement_reason = f"Deadline moved from {existing_by_number.deadline.date()} to {new_deadline.date()}"
                        postponed += 1
                
                # 📅 COMPREHENSIVE DATE VALIDATION (Extreme Accuracy for STC)
                date_validation_result = date_validator.validate_deadline(
                    new_deadline,
                    tender_data.get('published_at')
                )
                
                corrected_deadline = new_deadline  # Start with original
                
                if date_validation_result:
                    print(f"  📅 Date Validation: {date_validation_result.get('message', 'OK')}")
                    
                    # Auto-apply high-confidence corrections
                    if not date_validation_result.get('valid') and date_validation_result.get('valid') is not None:
                        print(f"  ⚠️  DATE ISSUE: {date_validation_result.get('issue')}")
                        
                        # Check suggestions and auto-apply if confidence >= 80%
                        for suggestion in date_validation_result.get('suggestions', []):
                            confidence = suggestion.get('confidence', 0)
                            print(f"  💡 Suggestion ({confidence:.0%} confidence):")
                            print(f"     Type: {suggestion.get('type')}")
                            print(f"     Reason: {suggestion.get('reason')}")
                            
                            if 'suggested' in suggestion:
                                suggested_date_str = suggestion.get('suggested')
                                original_date_str = suggestion.get('original')
                                print(f"     Suggested Date: {suggested_date_str}")
                                print(f"     Original Date: {original_date_str}")
                                
                                # AUTO-APPLY high-confidence corrections (>= 80%)
                                if confidence >= 0.80 and suggested_date_str:
                                    try:
                                        # Parse suggested date
                                        from datetime import datetime as dt
                                        corrected_deadline = dt.fromisoformat(suggested_date_str)
                                        if corrected_deadline.tzinfo is None:
                                            from datetime import timezone
                                            corrected_deadline = corrected_deadline.replace(tzinfo=timezone.utc)
                                        
                                        print(f"  ✅ AUTO-CORRECTED: {original_date_str} → {suggested_date_str}")
                                        print(f"     Reason: High confidence ({confidence:.0%}) correction applied")
                                        break  # Apply first high-confidence suggestion only
                                    except Exception as e:
                                        print(f"  ⚠️  Failed to parse suggested date: {e}")
                
                # Use corrected deadline (either original or auto-corrected)
                new_deadline = corrected_deadline
                
                # Clean ministry extraction: prioritize Claude over scraper, filter junk
                def is_valid_ministry(ministry_name):
                    """Filter out JUNK ministry names, but allow None/empty (valid for private sector)
                    
                    Note: Kuwait Al-Yawm publishes tenders from:
                    - Government ministries (وزارة...)
                    - Government companies (شركة...)
                    - Private companies (valid!)
                    - Authorities/Agencies (الهيئة، الإدارة...)
                    
                    So None/empty is VALID - only filter obvious garbage.
                    """
                    # None or empty is VALID (private sector, or AI couldn't extract)
                    if not ministry_name:
                        return True  # ✅ Allow None/empty
                    
                    # If something IS provided, validate it's not garbage
                    ministry_name = ministry_name.strip()
                    
                    # Too short after stripping = probably garbage
                    if len(ministry_name) < 3:
                        return False
                    
                    # Filter out pipe-heavy strings (table structures)
                    if ministry_name.count('|') > 3:
                        return False
                    
                    # Filter out number-heavy strings (page numbers)
                    digit_ratio = sum(c.isdigit() for c in ministry_name) / len(ministry_name)
                    if digit_ratio > 0.5:
                        return False
                    
                    # Filter out gazette headers
                    if 'الكويت اليوم' in ministry_name or 'كويت اليوم' in ministry_name or 'العدد' in ministry_name:
                        return False
                    
                    return True  # ✅ Accept anything else
                
                # Prioritize Claude extraction, fallback to scraper if needed
                ministry = extracted.get('ministry') if extracted else None
                if not is_valid_ministry(ministry):
                    ministry = tender_data.get('ministry') if is_valid_ministry(tender_data.get('ministry')) else None
                
                # Create tender
                tender = Tender(
                    title=tender_data['title'],
                    tender_number=tender_data.get('tender_number'),
                    url=tender_data['url'],
                    published_at=tender_data['published_at'],
                    deadline=new_deadline,
                    ministry=ministry,
                    category=tender_data.get('category'),
                    body=body_text,  # Now contains full PDF text or description
                    summary_ar=summary if tender_data.get('language') == 'ar' else summary_data.get('summary_ar', ''),
                    summary_en=summary if tender_data.get('language') == 'en' else summary_data.get('summary_en', ''),
                    facts_ar=summary_data.get('facts_ar', []),
                    facts_en=summary_data.get('facts_en', []),
                    lang=tender_data.get('language', 'ar'),
                    hash=tender_data['hash'],
                    attachments=None,
                    is_postponed=is_postponed,
                    original_deadline=original_deadline,
                    deadline_history=deadline_history,
                    postponement_reason=postponement_reason,
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
                
                # Enrich with AI in background (non-blocking)
                try:
                    from app.services.ai_enrichment import enrich_tender_with_ai
                    enrich_tender_with_ai(tender.id, db)
                except Exception as ai_error:
                    print(f"⚠️  AI enrichment skipped for tender {tender.id}: {ai_error}")
                
                processed += 1
                
            except Exception as e:
                print(f"Error processing tender: {e}")
                db.rollback()
                continue
        
        db.close()
        
        result = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "scraped": len(tenders),
            "processed": processed,
            "skipped": skipped,
            "postponed": postponed
        }
        
        print(f"✅ Weekly scrape completed: {result}")
        
        # 🤖 AUTOMATIC AI ENRICHMENT: Queue all newly processed tenders
        if processed > 0:
            print(f"🤖 Auto-queueing {processed} new tenders for AI enrichment...")
            try:
                # Get IDs of tenders without AI enrichment
                from app.workers.tender_tasks import enqueue_tender_enrichment
                from app.core.redis_config import get_task_queue
                
                db_new = SessionLocal()
                unenriched_tenders = db_new.query(Tender).filter(
                    Tender.ai_processed_at == None
                ).order_by(Tender.id.desc()).limit(processed).all()
                
                tender_ids = [t.id for t in unenriched_tenders]
                db_new.close()
                
                if tender_ids:
                    queue = get_task_queue()
                    if queue:
                        job_info = enqueue_tender_enrichment(tender_ids, queue)
                        print(f"✅ Queued {len(tender_ids)} tenders for AI enrichment: {job_info}")
                    else:
                        print(f"⚠️  Redis not available - AI enrichment skipped")
                else:
                    print(f"ℹ️  No new tenders to enrich")
                    
            except Exception as enrich_error:
                print(f"⚠️  Failed to queue AI enrichment: {enrich_error}")
                # Don't fail the whole scrape if enrichment queueing fails
        
    except Exception as e:
        print(f"❌ Error in weekly scrape: {e}")
        # Don't raise HTTPException in background task - just log it


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
