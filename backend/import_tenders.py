"""
Direct tender import script (without Celery)
Scrapes CAPT, processes with AI, and imports to database
"""
from sqlalchemy.orm import Session
from app.scraper.capt_scraper_lite import scrape_capt_lite
from app.ai.openai_service import OpenAIService
from app.db.session import SessionLocal
from app.models.tender import Tender, TenderEmbedding
from app.parser.pdf_parser import TextNormalizer


def import_tenders():
    print("Starting tender import...")
    print("=" * 70)
    
    # Scrape tenders (lightweight version)
    print("\n1️⃣  Scraping tenders from CAPT...")
    tenders = scrape_capt_lite()
    print(f"✅ Scraped {len(tenders)} tenders")
    
    if not tenders:
        print("⚠️  No tenders found. Exiting.")
        return
    
    # Initialize AI service
    print("\n2️⃣  Initializing AI services...")
    ai_service = OpenAIService()
    normalizer = TextNormalizer()
    
    # Process and import
    db = SessionLocal()
    try:
        processed = 0
        skipped = 0
        
        for i, tender_data in enumerate(tenders, 1):
            print(f"\n[{i}/{len(tenders)}] Processing: {tender_data['tender_number']}")
            
            # Check if already exists by hash (exact duplicate)
            existing = db.query(Tender).filter(Tender.hash == tender_data['hash']).first()
            if existing:
                print(f"  ⏭️  Skipped (duplicate)")
                skipped += 1
                continue
            
            # Check for same tender by number (to detect postponements)
            existing_by_number = db.query(Tender).filter(
                Tender.tender_number == tender_data.get('tender_number')
            ).first() if tender_data.get('tender_number') else None
            
            # Prepare text for AI
            text = f"{tender_data.get('title', '')}\\n{tender_data.get('description', '')}"
            if tender_data.get('language') == 'ar':
                text = normalizer.normalize_arabic(text)
            
            # AI Processing
            print(f"  🤖 AI processing...")
            
            # Extract structured data
            extracted = ai_service.extract_structured_data(text)
            
            # Generate summary  
            summary_data = ai_service.summarize_tender(
                tender_data.get('title', ''),
                tender_data.get('description', ''),
                tender_data.get('language', 'ar')
            )
            summary = summary_data.get('summary_ar', '') if tender_data.get('language') == 'ar' else summary_data.get('summary_en', '')
            
            # Generate embedding
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
                    print(f"  ⚠️  POSTPONEMENT DETECTED: {postponement_reason}")
            
            # Create tender record
            tender = Tender(
                title=tender_data['title'],
                tender_number=tender_data.get('tender_number'),
                url=tender_data['url'],
                published_at=tender_data['published_at'],
                deadline=new_deadline,
                ministry=tender_data.get('ministry', extracted.get('ministry')),
                category=tender_data.get('category'),
                body=tender_data.get('description', ''),
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
            db.flush()  # Get tender ID
            
            # Create embedding record
            tender_embedding = TenderEmbedding(
                tender_id=tender.id,
                embedding=embedding
            )
            db.add(tender_embedding)
            
            db.commit()
            processed += 1
            print(f"  ✅ Imported successfully")
        
        print("\n" + "=" * 70)
        print(f"📊 Import Summary:")
        print(f"   Total scraped: {len(tenders)}")
        print(f"   Newly imported: {processed}")
        print(f"   Skipped (duplicates): {skipped}")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import_tenders()
