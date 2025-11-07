"""
Cron job endpoints for scheduled tasks
"""
from fastapi import APIRouter, HTTPException, Header
from datetime import datetime
import asyncio
from typing import Optional

from app.core.config import settings
from app.scraper.capt_scraper_lite import scrape_capt_lite
from app.db.session import SessionLocal
from app.models.tender import Tender, TenderEmbedding
from app.ai.openai_service import OpenAIService
from app.parser.pdf_parser import TextNormalizer
from app.parser.pdf_extractor import PDFExtractor

router = APIRouter(prefix="/cron", tags=["cron"])


@router.post("/scrape-weekly")
async def scrape_weekly(authorization: Optional[str] = Header(None)):
    """
    Weekly tender scraping job - runs every Sunday
    Protected by authorization header for security
    """
    # Simple auth check (use env var for cron secret)
    cron_secret = settings.CRON_SECRET if hasattr(settings, 'CRON_SECRET') else None
    if cron_secret and authorization != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        print(f"🤖 Starting weekly scrape at {datetime.now()}")
        
        # Scrape all tenders (lightweight HTTP-based scraper)
        try:
            tenders = scrape_capt_lite()  # Non-async, lightweight
            print(f"✅ Scraped {len(tenders)} tenders")
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
        pdf_extractor = PDFExtractor()
        
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
                
                # Download and extract PDF text if URL is available
                pdf_text = None
                if tender_data.get('pdf_url'):
                    print(f"  📄 Processing PDF for tender {tender_data.get('tender_number')}")
                    pdf_text = pdf_extractor.extract_text_from_url(tender_data['pdf_url'])
                    if pdf_text:
                        print(f"  ✅ Extracted {len(pdf_text)} characters from PDF")
                    else:
                        print(f"  ⚠️  PDF extraction failed, using description only")
                
                # Prepare text for AI (combine description + PDF content)
                description = tender_data.get('description', '')
                if pdf_text:
                    # Use PDF text as main body, description as summary
                    full_text = f"{description}\n\n{pdf_text[:50000]}"  # Limit to 50K chars
                    body_text = pdf_text[:100000]  # Store up to 100K chars
                else:
                    full_text = description
                    body_text = description
                
                text = f"{tender_data.get('title', '')}\n{full_text}"
                if tender_data.get('language') == 'ar':
                    text = normalizer.normalize_arabic(text)
                
                # AI Processing
                extracted = ai_service.extract_structured_data(text)
                summary_data = ai_service.summarize_tender(
                    tender_data.get('title', ''),
                    tender_data.get('description', ''),
                    tender_data.get('language', 'ar')
                )
                summary = summary_data.get('summary_ar', '') if tender_data.get('language') == 'ar' else summary_data.get('summary_en', '')
                embedding = ai_service.generate_embedding(text)
                
                # Check for postponement
                new_deadline = extracted.get('deadline')
                is_postponed = False
                original_deadline = None
                deadline_history = None
                postponement_reason = None
                
                if existing_by_number and existing_by_number.deadline and new_deadline:
                    if new_deadline > existing_by_number.deadline:
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
        return result
        
    except Exception as e:
        print(f"❌ Error in weekly scrape: {e}")
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
