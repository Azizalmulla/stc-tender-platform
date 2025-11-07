# Google Cloud Document AI Setup Guide

## ✅ You've Already Enabled the API

Great! You've enabled **Cloud Document AI API** in your Google Cloud Console.

---

## 📋 Next Steps

### 1. Create a Document Processor

1. Go to: https://console.cloud.google.com/ai/document-ai/processors
2. Click **"Create Processor"**
3. Choose **"Form Parser"** (best for structured documents like tenders)
4. Select region: **us** or **eu** (us is usually faster)
5. Give it a name: e.g., "Kuwait Tender Parser"
6. Click **Create**

### 2. Get Your Processor ID

After creating the processor, you'll see a screen with processor details:
- Copy the **Processor ID** (looks like: `abc123def456`)
- Note your **Project ID** and **Location**

Your processor name format will be:
```
projects/YOUR_PROJECT_ID/locations/us/processors/YOUR_PROCESSOR_ID
```

Example:
```
projects/stcnews/locations/us/processors/3f2a8b9c4d5e6f7g
```

### 3. Create Service Account Credentials

1. Go to: https://console.cloud.google.com/iam-admin/serviceaccounts
2. Click **"Create Service Account"**
3. Name: `tender-scraper-sa`
4. Click **Create and Continue**
5. Grant role: **"Document AI API User"**
6. Click **Done**
7. Click on the service account you just created
8. Go to **"Keys"** tab
9. Click **"Add Key"** → **"Create new key"**
10. Choose **JSON**
11. Download the JSON file (keep it secure!)

### 4. Configure Your .env File

Update `/backend/.env`:

```env
# Google Cloud Document AI
GOOGLE_CLOUD_DOCUMENTAI_CREDENTIALS=/path/to/your-service-account-key.json
DOCUMENTAI_PROCESSOR_NAME=projects/YOUR_PROJECT_ID/locations/us/processors/YOUR_PROCESSOR_ID
```

**Example:**
```env
GOOGLE_CLOUD_DOCUMENTAI_CREDENTIALS=/Users/azizalmulla/Desktop/stc/gcp-credentials.json
DOCUMENTAI_PROCESSOR_NAME=projects/stcnews/locations/us/processors/3f2a8b9c4d5e6f7g
```

---

## 🧪 Test Document AI

Create a test script to verify it works:

```bash
cd backend
source venv/bin/activate
python -c "
from app.parser.pdf_parser import PDFParser
parser = PDFParser()
print('Document AI configured:', parser.documentai_client is not None)
"
```

---

## 💰 Pricing

- **First 1,000 pages/month**: FREE
- **After that**: $1.50 per 1,000 pages
- Form Parser can extract:
  - Text (like Vision AI)
  - Tables (key-value pairs)
  - Form fields (automatic detection)

For your use case (processing ~200-500 tender PDFs/month):
- Estimated cost: **$1-3/month**

---

## 🎯 Why This is Better than Vision AI

1. **Structured extraction**: Automatically finds tender numbers, deadlines, amounts
2. **Table handling**: Extracts pricing tables, specifications
3. **Form fields**: Understands document structure
4. **Same API**: Same authentication, same pricing tier
5. **Better accuracy**: Designed for documents, not just images

---

## 🔧 Alternative: Skip Document AI for Now

If you want to test without Document AI first:
- The app will fall back to native PDF text extraction
- Works for ~70% of tenders (those with embedded text)
- You can add Document AI later when you're ready

---

## 📞 Need Help?

**Finding your processor name:**
1. Go to Document AI console
2. Click on your processor
3. Look at the URL or processor details
4. Format: `projects/{project}/locations/{location}/processors/{processor}`

**Common issues:**
- Make sure service account has "Document AI API User" role
- Make sure the JSON key file path is absolute (not relative)
- Make sure you're using the correct processor name format

---

**You're all set!** Once configured, the system will automatically use Document AI for PDF tenders that don't have extractable text.
