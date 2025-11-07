"""
Direct tender import script (without Celery)
Scrapes CAPT, processes with AI, and imports to database
"""
import asyncio
from sqlalchemy.orm import Session
from app.scraper.capt_scraper import scrape_capt
from app.ai.openai_service import OpenAIService
from app.db.session import SessionLocal
from app.models.tender import Tender, TenderEmbedding
from app.parser.pdf_parser import TextNormalizer


def import_tenders():
    print("Starting tender import...")
    print("=" * 70)
    
    # Scrape tenders
    print("\n1️⃣  Scraping tenders from CAPT...")
    tenders = asyncio.run(scrape_capt())
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
            
            # Check if already exists
            existing = db.query(Tender).filter(Tender.hash == tender_data['hash']).first()
            if existing:
                print(f"  ⏭️  Skipped (duplicate)")
                skipped += 1
                continue
            
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
            
            # Create tender record
            tender = Tender(
                title=tender_data['title'],
                tender_number=tender_data.get('tender_number'),
                url=tender_data['url'],
                published_at=tender_data['published_at'],
                deadline=extracted.get('deadline'),
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
