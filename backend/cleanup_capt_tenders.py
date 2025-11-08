"""
Script to remove all CAPT tenders from the database
Run this once to clean up old CAPT data before Kuwait Alyom scraper takes over
"""

from app.db.session import SessionLocal
from app.models.tender import Tender
from sqlalchemy import func

def cleanup_capt_tenders():
    db = SessionLocal()
    try:
        # Count CAPT tenders before deletion
        capt_count = db.query(func.count(Tender.id)).filter(
            Tender.url.like('%capt.gov.kw%')
        ).scalar()
        
        print(f"Found {capt_count} CAPT tenders to delete")
        
        if capt_count == 0:
            print("No CAPT tenders found. Exiting.")
            return
        
        # Confirm deletion
        confirm = input(f"Are you sure you want to delete {capt_count} CAPT tenders? (yes/no): ")
        
        if confirm.lower() != 'yes':
            print("Deletion cancelled.")
            return
        
        # Delete CAPT tenders
        deleted = db.query(Tender).filter(
            Tender.url.like('%capt.gov.kw%')
        ).delete(synchronize_session=False)
        
        db.commit()
        
        print(f"✅ Successfully deleted {deleted} CAPT tenders")
        
        # Count remaining tenders
        remaining = db.query(func.count(Tender.id)).scalar()
        print(f"📊 Remaining tenders in database: {remaining}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error during deletion: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_capt_tenders()
