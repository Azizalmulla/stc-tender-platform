#!/usr/bin/env python
"""
Clear all tenders from the database
WARNING: This will delete ALL tender data!
"""
import sys
from sqlalchemy import text
from app.db.session import SessionLocal, engine
from app.models.tender import Tender, TenderEmbedding


def confirm_clear():
    """Ask for confirmation before clearing"""
    print("\n⚠️  WARNING: This will DELETE ALL tender data from the database!")
    print("   - All tenders will be removed")
    print("   - All embeddings will be removed")
    print("   - This action CANNOT be undone!")
    print()
    
    response = input("Are you sure you want to continue? Type 'YES' to confirm: ")
    return response.strip() == "YES"


def clear_database():
    """Clear all tender data from database"""
    try:
        db = SessionLocal()
        
        print("\n🗑️  Clearing database...")
        
        # Count before deletion
        tender_count = db.query(Tender).count()
        embedding_count = db.query(TenderEmbedding).count()
        
        print(f"   Found {tender_count} tenders")
        print(f"   Found {embedding_count} embeddings")
        
        if tender_count == 0 and embedding_count == 0:
            print("\n✅ Database is already empty!")
            return
        
        # Delete all embeddings first (foreign key constraint)
        print("\n   Deleting embeddings...")
        db.query(TenderEmbedding).delete()
        db.commit()
        print(f"   ✅ Deleted {embedding_count} embeddings")
        
        # Delete all tenders
        print("   Deleting tenders...")
        db.query(Tender).delete()
        db.commit()
        print(f"   ✅ Deleted {tender_count} tenders")
        
        # Reset sequences (for auto-increment IDs) - optional, may not exist
        print("\n   Resetting ID sequences...")
        try:
            db.execute(text("ALTER SEQUENCE tenders_id_seq RESTART WITH 1"))
            print("   ✅ Tenders sequence reset")
        except Exception as e:
            print(f"   ⚠️  Tenders sequence not reset (may not exist): {e}")
        
        try:
            db.execute(text("ALTER SEQUENCE tender_embeddings_id_seq RESTART WITH 1"))
            print("   ✅ Embeddings sequence reset")
        except Exception as e:
            print(f"   ⚠️  Embeddings sequence not reset (may not exist): {e}")
        
        db.commit()
        
        # Verify
        remaining_tenders = db.query(Tender).count()
        remaining_embeddings = db.query(TenderEmbedding).count()
        
        print(f"\n✅ Database cleared successfully!")
        print(f"   Remaining tenders: {remaining_tenders}")
        print(f"   Remaining embeddings: {remaining_embeddings}")
        
        db.close()
        
    except Exception as e:
        print(f"\n❌ Error clearing database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point"""
    print("=" * 60)
    print("DATABASE CLEAR UTILITY")
    print("=" * 60)
    
    if not confirm_clear():
        print("\n❌ Operation cancelled by user")
        sys.exit(0)
    
    clear_database()
    
    print("\n" + "=" * 60)
    print("✅ Done! Database is now empty and ready for fresh scrape.")
    print("=" * 60)


if __name__ == "__main__":
    main()
