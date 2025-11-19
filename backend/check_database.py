#!/usr/bin/env python
"""
Check database status
"""
from app.db.session import SessionLocal
from app.models.tender import Tender, TenderEmbedding


def check_database():
    """Check current database status"""
    db = SessionLocal()
    
    tender_count = db.query(Tender).count()
    embedding_count = db.query(TenderEmbedding).count()
    
    print("\n" + "=" * 60)
    print("DATABASE STATUS")
    print("=" * 60)
    print(f"Tenders: {tender_count}")
    print(f"Embeddings: {embedding_count}")
    print("=" * 60 + "\n")
    
    if tender_count == 0:
        print("✅ Database is empty and ready for fresh scrape!")
    else:
        print(f"⚠️  Database still has {tender_count} tenders")
    
    db.close()


if __name__ == "__main__":
    check_database()
