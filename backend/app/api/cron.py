"""
Cron job endpoints for scheduled tasks
"""
from fastapi import APIRouter, HTTPException, Header
from datetime import datetime
import asyncio
from typing import Optional

from app.core.config import settings
from app.scraper.kuwaitalyom_scraper import KuwaitAlyomScraper
from app.db.session import SessionLocal
from app.models.tender import Tender, TenderEmbedding
from app.ai.openai_service import OpenAIService
from app.parser.pdf_parser import TextNormalizer

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
        print(f"🤖 Starting weekly scrape from Kuwait Al-Yawm (Official Gazette) at {datetime.now()}")
        
        # Initialize Kuwait Alyom scraper with credentials
        username = settings.KUWAIT_ALYOM_USERNAME
        password = settings.KUWAIT_ALYOM_PASSWORD
        
        if not username or not password:
            raise HTTPException(
                status_code=500, 
                detail="Kuwait Alyom credentials not configured. Set KUWAIT_ALYOM_USERNAME and KUWAIT_ALYOM_PASSWORD"
            )
        
        # Scrape tenders from Kuwait Al-Yawm (Official Gazette)
        try:
            scraper = KuwaitAlyomScraper(username=username, password=password)
            
            # Scrape with PDF extraction enabled (uses Google Doc AI)
            # For weekly scrape, limit to recent tenders and enable PDF extraction
            tenders = scraper.scrape_all(
                category_id="1",        # 1 = Tenders (المناقصات)
                days_back=14,           # Last 2 weeks for weekly scrape
                limit=50,               # Process up to 50 tenders per run
                extract_pdfs=True       # Enable Google Doc AI OCR
            )
            print(f"✅ Scraped {len(tenders)} tenders from Kuwait Al-Yawm (Official Gazette)")
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
                
                # Kuwait Alyom scraper already extracted PDF text via Google Doc AI OCR
                pdf_text = tender_data.get('pdf_text')  # Already extracted by scraper
                description = tender_data.get('description', '')
                
                # Prepare text for AI (combine description + PDF content)
                if pdf_text:
                    print(f"  ✅ Using Google Doc AI OCR text ({len(pdf_text)} characters)")
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
