# Integration Guide: New OCR Pipeline

## 🎯 **How to Switch from Old to New Pipeline**

---

## **Step 1: Test First** ⚠️

**CRITICAL:** Test the new pipeline before integrating!

```bash
cd /Users/azizalmulla/Desktop/stc/backend
python test_new_pipeline.py 3715 144
```

**What to verify:**
- ✅ PDF downloads successfully
- ✅ Text length is 800-2000 chars (not 100-200)
- ✅ Quality score is > 0.7
- ✅ Text is readable Arabic (not gibberish)
- ✅ Ministry is extracted
- ✅ No hallucinations in extracted fields

**If test fails:** Debug issues before proceeding!

---

## **Step 2: Update Main Scraper Method**

### **Current Code (Around line 1250 in `kuwaitalyom_scraper.py`):**

```python
def _extract_tender_data(self, tender_card: dict, category_id: int) -> Optional[dict]:
    """Extract full tender details from a tender card"""
    
    # ... existing code ...
    
    # Extract PDF content if available
    if extract_pdf and edition_id and page_number:
        pdf_content = self._extract_text_from_page(edition_id, page_number)
        
        if pdf_content:
            body = pdf_content.get('text')
            ministry_from_vision = pdf_content.get('ministry')
            
            if ministry_from_vision:
                ministry = ministry_from_vision
```

### **NEW Code (Replace the above section):**

```python
def _extract_tender_data(self, tender_card: dict, category_id: int) -> Optional[dict]:
    """Extract full tender details from a tender card"""
    
    # ... existing code ...
    
    # Extract PDF content if available
    if extract_pdf and edition_id and page_number:
        # Try new production pipeline first
        pdf_content = self._extract_tender_with_new_pipeline(edition_id, page_number)
        
        if pdf_content and pdf_content.get('validation', {}).get('is_acceptable', False):
            # New pipeline succeeded with acceptable quality
            body = pdf_content.get('text')
            ministry_from_extraction = pdf_content.get('ministry')
            extracted_fields = pdf_content.get('extracted_fields', {})
            quality_score = pdf_content.get('validation', {}).get('quality_score', 0)
            
            print(f"✅ New pipeline succeeded (quality: {quality_score})")
            
            # Use extracted ministry if found
            if ministry_from_extraction and not ministry:
                ministry = ministry_from_extraction
            
            # Use extracted tender number if not found yet
            if not tender_number and extracted_fields.get('tender_number'):
                tender_number = extracted_fields['tender_number']
            
            # Store quality metadata
            tender_data['quality_score'] = quality_score
            tender_data['extraction_method'] = 'pdf_pipeline_v2'
            
        else:
            # New pipeline failed or poor quality, fallback to old method
            print(f"⚠️  New pipeline failed or poor quality, using fallback...")
            pdf_content = self._extract_text_from_page(edition_id, page_number)
            
            if pdf_content:
                body = pdf_content.get('text')
                ministry_from_vision = pdf_content.get('ministry')
                
                if ministry_from_vision:
                    ministry = ministry_from_vision
                
                tender_data['quality_score'] = 0.5  # Estimated for old method
                tender_data['extraction_method'] = 'screenshot_fallback'
```

---

## **Step 3: Update Database Schema (Optional but Recommended)**

Add columns to track quality:

```sql
ALTER TABLE tenders 
ADD COLUMN quality_score FLOAT DEFAULT NULL,
ADD COLUMN extraction_method VARCHAR(50) DEFAULT NULL,
ADD COLUMN validation_issues JSONB DEFAULT NULL,
ADD COLUMN extracted_fields JSONB DEFAULT NULL;
```

**Or in your Tender model (`backend/app/models/tender.py`):**

```python
class Tender(Base):
    # ... existing fields ...
    
    quality_score = Column(Float, nullable=True)
    extraction_method = Column(String(50), nullable=True)
    validation_issues = Column(JSONB, nullable=True)
    extracted_fields = Column(JSONB, nullable=True)
```

---

## **Step 4: Update Summarization to Use Better Text**

### **Current Code (`backend/app/api/cron.py`):**

```python
# Generate AI summary
if tender_data['body']:
    summary_result = openai_service.summarize_tender(
        title=tender_data['title'],
        body=tender_data['body']
    )
```

### **Keep as-is!**

The new pipeline already stores cleaned text in `tender_data['body']`, so summarization will automatically use better quality text.

**No changes needed here!** ✅

---

## **Step 5: Update Frontend Display (Optional)**

Show quality indicators in UI:

### **In tender details page:**

```typescript
// Show quality badge
{tender.quality_score && (
  <Badge variant={tender.quality_score > 0.7 ? "success" : "warning"}>
    Quality: {(tender.quality_score * 100).toFixed(0)}%
  </Badge>
)}

// Show validation warnings
{tender.validation_issues && tender.validation_issues.length > 0 && (
  <Alert variant="warning">
    <AlertTitle>Quality Issues Detected</AlertTitle>
    <ul>
      {tender.validation_issues.map((issue, i) => (
        <li key={i}>{issue}</li>
      ))}
    </ul>
  </Alert>
)}
```

---

## **Step 6: Deploy Strategy**

### **Conservative Approach (Recommended):**

1. **Deploy code** (new pipeline available but not default)
2. **Test on production** with a few tenders manually
3. **Switch to new pipeline** by updating `_extract_tender_data`
4. **Clear database** and rescrape
5. **Monitor quality scores** in logs
6. **Rollback if needed** (keep old method as fallback)

### **Aggressive Approach:**

1. **Deploy all changes** including database schema
2. **Clear database immediately**
3. **Rescrape with new pipeline**
4. **Hope for the best** 🤞

**Recommendation:** Use conservative approach!

---

## **Step 7: Monitoring After Deploy**

### **Check these metrics in logs:**

```bash
# Count how many used new pipeline vs fallback
grep "New pipeline succeeded" render_logs.txt | wc -l
grep "using fallback" render_logs.txt | wc -l

# Check average quality scores
grep "quality:" render_logs.txt

# Check for hallucination warnings
grep "hallucination" render_logs.txt

# Check text lengths
grep "Text length:" render_logs.txt
```

### **Success Criteria:**

- ✅ 80%+ tenders use new pipeline (not fallback)
- ✅ Average quality score > 0.7
- ✅ Average text length > 500 chars
- ✅ < 5% hallucination warnings
- ✅ Ministry extraction rate > 70%
- ✅ No JSON parsing errors
- ✅ No base64 decode errors

---

## **Rollback Plan**

If new pipeline fails in production:

### **Quick Rollback:**

```python
# In _extract_tender_data, simply comment out new pipeline:

# pdf_content = self._extract_tender_with_new_pipeline(edition_id, page_number)
# Use old method directly:
pdf_content = self._extract_text_from_page(edition_id, page_number)
```

Then:
1. Git commit
2. Push to GitHub
3. Render auto-deploys
4. Back to old behavior in 2-3 minutes

---

## **Testing Checklist Before Deploy**

- [ ] Ran `python test_new_pipeline.py 3715 144`
- [ ] Verified text length is 800-2000 chars
- [ ] Verified quality score > 0.7
- [ ] Verified ministry extracted
- [ ] Verified no hallucinations
- [ ] Tested batch mode on 5 pages
- [ ] Checked all 5 pages succeeded
- [ ] Updated `_extract_tender_data` method
- [ ] Database schema updated (if needed)
- [ ] Git committed changes
- [ ] Pushed to GitHub
- [ ] Tested on Render staging (if available)
- [ ] Ready to deploy to production

---

## **Estimated Timeline**

| Task | Time |
|------|------|
| Test new pipeline | 15 mins |
| Update `_extract_tender_data` | 10 mins |
| Update database schema | 15 mins |
| Deploy to Render | 5 mins |
| Clear database | 1 min |
| Run full scrape | 30 mins |
| Verify quality | 15 mins |
| **Total** | **~1.5 hours** |

---

## **Quick Commands Reference**

```bash
# Test new pipeline
python test_new_pipeline.py 3715 144

# Test batch
python test_new_pipeline.py 3715 144 5

# Deploy
git add -A
git commit -m "feat: Implement production-quality OCR pipeline"
git push origin main

# Clear database (after deploy)
curl -X POST "https://stc-tender-platform.onrender.com/api/cron/clear-database" \
  -H "Authorization: Bearer YOUR_CRON_SECRET"

# Start scrape
curl -X POST "https://stc-tender-platform.onrender.com/api/cron/scrape-weekly" \
  -H "Authorization: Bearer YOUR_CRON_SECRET"
```

---

**Ready to integrate when you're ready!** 🚀

Just test first, then follow steps 2-7 when quality looks good.
