"""
Test script for new OCR pipeline
Tests the complete production-quality extraction pipeline without modifying scraper

Usage:
    python test_new_pipeline.py <edition_id> <page_number>
    
Example:
    python test_new_pipeline.py 3715 144
"""

import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from scraper.kuwaitalyom_scraper import KuwaitAlyomScraper
from dotenv import load_dotenv

def test_new_pipeline(edition_id: int, page_number: int):
    """Test the new extraction pipeline on a specific page"""
    
    print(f"\n{'='*80}")
    print(f"TESTING NEW PIPELINE")
    print(f"Edition: {edition_id}, Page: {page_number}")
    print(f"{'='*80}\n")
    
    # Load environment variables
    load_dotenv()
    
    # Initialize scraper
    scraper = KuwaitAlyomScraper()
    
    # Login
    print("🔐 Logging in...")
    if not scraper.login():
        print("❌ Login failed")
        return False
    print("✅ Login successful\n")
    
    # Test new pipeline
    result = scraper._extract_tender_with_new_pipeline(edition_id, page_number)
    
    if not result:
        print("\n❌ PIPELINE FAILED - No result returned")
        return False
    
    # Display results
    print("\n" + "="*80)
    print("📊 EXTRACTION RESULTS")
    print("="*80)
    
    print(f"\n📏 Text Length: {len(result['text'])} characters")
    print(f"📊 Quality Score: {result['validation']['quality_score']}")
    print(f"📈 Arabic Ratio: {result['validation']['arabic_ratio']*100:.1f}%")
    print(f"🏢 Ministry: {result['ministry'] or 'Not extracted'}")
    print(f"✅ Acceptable: {result['validation']['is_acceptable']}")
    
    if result['validation']['issues']:
        print(f"\n⚠️  Issues Found:")
        for issue in result['validation']['issues']:
            print(f"   - {issue}")
    
    print(f"\n📋 Extracted Fields:")
    fields = result['extracted_fields']
    print(f"   - Title: {fields.get('title') or 'N/A'}")
    print(f"   - Tender Number: {fields.get('tender_number') or 'N/A'}")
    print(f"   - Requirements: {len(fields.get('requirements', []))} items")
    if fields.get('requirements'):
        for i, req in enumerate(fields['requirements'][:3], 1):
            print(f"      {i}. {req[:60]}...")
    print(f"   - Deadline: {fields.get('deadline_text') or 'N/A'}")
    print(f"   - Contact: {fields.get('contact_info') or 'N/A'}")
    print(f"   - Budget: {fields.get('budget_text') or 'N/A'}")
    
    print(f"\n📄 Full Text Preview (first 500 chars):")
    print("-" * 80)
    print(result['text'][:500])
    if len(result['text']) > 500:
        print("\n... (truncated) ...")
    print("-" * 80)
    
    print(f"\n📄 Full Text Preview (last 300 chars):")
    print("-" * 80)
    print(result['text'][-300:])
    print("-" * 80)
    
    # Compare with old method
    print("\n" + "="*80)
    print("🔄 COMPARING WITH OLD PIPELINE (Screenshot method)")
    print("="*80 + "\n")
    
    old_result = scraper._extract_text_from_page(edition_id, page_number)
    
    if old_result:
        old_text = old_result.get('text', '')
        print(f"📏 Old Method Text Length: {len(old_text)} characters")
        print(f"📏 New Method Text Length: {len(result['text'])} characters")
        print(f"📊 Improvement: {len(result['text']) - len(old_text):+d} chars ({((len(result['text'])/len(old_text) - 1) * 100) if old_text else 0:+.1f}%)")
        
        print(f"\n📄 Old Method Preview (first 300 chars):")
        print("-" * 80)
        print(old_text[:300])
        print("-" * 80)
    else:
        print("❌ Old method failed to extract text")
    
    print("\n" + "="*80)
    print("✅ TEST COMPLETE")
    print("="*80)
    
    return True

def compare_multiple_pages(edition_id: int, start_page: int, count: int = 5):
    """Test multiple pages and show statistics"""
    
    print(f"\n{'='*80}")
    print(f"BATCH TEST: {count} pages starting from page {start_page}")
    print(f"{'='*80}\n")
    
    load_dotenv()
    scraper = KuwaitAlyomScraper()
    
    if not scraper.login():
        print("❌ Login failed")
        return
    
    results = []
    
    for i in range(count):
        page = start_page + i
        print(f"\n{'─'*80}")
        print(f"Testing page {page} ({i+1}/{count})")
        print(f"{'─'*80}")
        
        result = scraper._extract_tender_with_new_pipeline(edition_id, page)
        
        if result:
            results.append({
                'page': page,
                'length': len(result['text']),
                'quality': result['validation']['quality_score'],
                'acceptable': result['validation']['is_acceptable'],
                'ministry': result['ministry']
            })
    
    # Show summary
    print(f"\n{'='*80}")
    print(f"📊 BATCH RESULTS SUMMARY")
    print(f"{'='*80}\n")
    
    if results:
        avg_length = sum(r['length'] for r in results) / len(results)
        avg_quality = sum(r['quality'] for r in results) / len(results)
        acceptable_count = sum(1 for r in results if r['acceptable'])
        ministry_count = sum(1 for r in results if r['ministry'])
        
        print(f"✅ Successful: {len(results)}/{count} pages")
        print(f"📏 Average Length: {avg_length:.0f} characters")
        print(f"📊 Average Quality: {avg_quality:.2f}")
        print(f"✅ Acceptable Quality: {acceptable_count}/{len(results)} ({acceptable_count/len(results)*100:.1f}%)")
        print(f"🏢 Ministry Extracted: {ministry_count}/{len(results)} ({ministry_count/len(results)*100:.1f}%)")
        
        print(f"\n📋 Individual Results:")
        for r in results:
            status = "✅" if r['acceptable'] else "⚠️"
            print(f"   {status} Page {r['page']}: {r['length']} chars, quality {r['quality']:.2f}, ministry: {r['ministry'] or 'N/A'}")
    else:
        print("❌ No successful extractions")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_new_pipeline.py <edition_id> <page_number> [batch_count]")
        print("\nExamples:")
        print("  python test_new_pipeline.py 3715 144")
        print("  python test_new_pipeline.py 3715 144 5  # Test 5 pages starting from 144")
        sys.exit(1)
    
    edition_id = int(sys.argv[1])
    page_number = int(sys.argv[2])
    
    if len(sys.argv) > 3:
        # Batch test
        count = int(sys.argv[3])
        compare_multiple_pages(edition_id, page_number, count)
    else:
        # Single page test
        success = test_new_pipeline(edition_id, page_number)
        sys.exit(0 if success else 1)
