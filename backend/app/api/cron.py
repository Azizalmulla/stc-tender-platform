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
from app.ai.openai_service import OpenAIService  # Only for embeddings
from app.ai.mistral_service import mistral_service  # Primary: Mistral for all AI tasks
from app.ai.claude_service import claude_service  # Fallback: Claude if Mistral fails
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
                    days_back=14,           # Last 2 weeks for weekly scrape
                    limit=10,               # 🧪 TESTING: Small batch for quick validation
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
        ai_service = OpenAIService()
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
                
                # Kuwait Alyom scraper already extracted PDF text via Claude Sonnet 4.5 OCR
                pdf_text = tender_data.get('pdf_text')  # Already extracted by scraper
                description = tender_data.get('description', '')
                
                # Prepare text for AI (combine description + PDF content)
                if pdf_text:
                    print(f"  ✅ Using OCR extracted text ({len(pdf_text)} characters)")
                    # Use PDF text as main body, description as summary
                    full_text = f"{description}\n\n{pdf_text[:50000]}"  # Limit to 50K chars
                    body_text = pdf_text[:100000]  # Store up to 100K chars
                else:
                    print(f"  ⚠️  No PDF text available, using metadata only")
                    full_text = description
                    body_text = description
                
                text = f"{tender_data.get('title', '')}\n{full_text}"
                if tender_data.get('language') == 'ar':
                    text = normalizer.normalize_arabic(text)
                
                # ============================================
                # SMART HYBRID: Claude Reasoning (Primary) → Mistral (Fallback)
                # Note: Mistral OCR is still primary for text extraction (in scraper)
                # ============================================
                
                # Try Claude first for summarization & extraction (more reliable for critical data)
                extracted = None
                summary_data = None
                
                try:
                    print(f"  🧠 Using Claude Sonnet 4.5 for summarization and extraction (primary)...")
                    
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
                    print(f"  ⚠️  Claude failed: {e}, falling back to Mistral...")
                    extracted = None
                    summary_data = None
                
                # Fallback to Mistral if Claude failed
                if (not extracted or not summary_data) and mistral_service:
                    try:
                        print(f"  🚀 Using Mistral Large for summarization and extraction (fallback)...")
                        
                        # Structured extraction with Mistral
                        extracted = mistral_service.extract_structured_data(text)
                        
                        # Summarization with Mistral
                        if extracted and extracted.get('success'):
                            summary_data = mistral_service.summarize_tender(
                                full_text,
                                tender_number=extracted.get('tender_number'),
                                entity=extracted.get('ministry'),
                                deadline=extracted.get('deadline')
                            )
                        
                        if extracted and extracted.get('success') and summary_data and summary_data.get('success'):
                            print(f"  ✅ Mistral AI processing successful")
                    
                    except Exception as e:
                        print(f"  ❌ Mistral also failed: {e}")
                
                summary = summary_data.get('summary_ar', '') if tender_data.get('language') == 'ar' else summary_data.get('summary_en', '')
                
                # OpenAI only for embeddings (Claude doesn't have embeddings API)
                embedding = ai_service.generate_embedding(text)
                
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
                
                if date_validation_result:
                    print(f"  📅 Date Validation: {date_validation_result.get('message', 'OK')}")
                    
                    # Log issues
                    if not date_validation_result.get('valid') and date_validation_result.get('valid') is not None:
                        print(f"  ⚠️  DATE ISSUE: {date_validation_result.get('issue')}")
                        
                        # Log suggestions if available
                        for suggestion in date_validation_result.get('suggestions', []):
                            print(f"  💡 Suggestion ({suggestion.get('confidence', 0):.0%} confidence):")
                            print(f"     Type: {suggestion.get('type')}")
                            print(f"     Reason: {suggestion.get('reason')}")
                            if 'suggested' in suggestion:
                                print(f"     Suggested Date: {suggestion.get('suggested')}")
                                print(f"     Original Date: {suggestion.get('original')}")
                
                # Create tender
                tender = Tender(
                    title=tender_data['title'],
                    tender_number=tender_data.get('tender_number'),
                    url=tender_data['url'],
                    published_at=tender_data['published_at'],
                    deadline=new_deadline,
                    ministry=tender_data.get('ministry', extracted.get('ministry')),
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
        from app.ai.openai_service import OpenAIService
        
        db = SessionLocal()
        ai_service = OpenAIService()
        
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
                
                # Generate embedding
                embedding = ai_service.generate_embedding(text)
                
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
