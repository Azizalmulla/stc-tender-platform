# 🤖 Automatic Scraping Setup Guide

## Overview

Your platform now has automatic scraping configured to run:
- **Every Sunday at 8 AM Kuwait Time**: Full scrape of all tenders
- **Daily (Mon-Sat) at 8 AM Kuwait Time**: Quick postponement check

---

## 🔐 Security Setup

### 1. Generate CRON_SECRET

In your terminal, generate a random secret:

```bash
openssl rand -hex 32
```

Copy the output (e.g., `a1b2c3d4e5f6...`)

### 2. Add to Render Environment Variables

1. Go to your Render dashboard: https://dashboard.render.com
2. Select **stc-tender-api** service
3. Click **Environment** tab
4. Add new variable:
   - **Key**: `CRON_SECRET`
   - **Value**: (paste your generated secret)
5. Click **Save**

---

## ⏰ Setup Cron Jobs on Render

### Option 1: Using Render Cron Jobs (Recommended)

1. Go to Render Dashboard
2. Click **New +** → **Cron Job**

#### Weekly Sunday Scraper:

**Name**: `stc-tender-weekly-scraper`

**Command**:
```bash
curl -X POST https://stc-tender-platform.onrender.com/api/cron/scrape-weekly -H "Authorization: Bearer YOUR_CRON_SECRET_HERE"
```

**Schedule**: `0 5 * * 0` (Every Sunday at 5 AM UTC = 8 AM Kuwait)

**Docker Image**: Use same Docker image as your web service

---

#### Daily Postponement Check:

**Name**: `stc-tender-daily-check`

**Command**:
```bash
curl -X POST https://stc-tender-platform.onrender.com/api/cron/check-postponements -H "Authorization: Bearer YOUR_CRON_SECRET_HERE"
```

**Schedule**: `0 5 * * 1-6` (Monday-Saturday at 5 AM UTC = 8 AM Kuwait)

---

### Option 2: Using External Cron Service (EasyCron, cron-job.org)

1. Sign up at https://cron-job.org (free)
2. Create new cron job:
   - **URL**: `https://stc-tender-platform.onrender.com/api/cron/scrape-weekly`
   - **Schedule**: Every Sunday at 05:00 UTC
   - **Custom Header**: 
     - Name: `Authorization`
     - Value: `Bearer YOUR_CRON_SECRET`

---

## 🧪 Testing

### Test Weekly Scraper Manually:

```bash
curl -X POST https://stc-tender-platform.onrender.com/api/cron/scrape-weekly \
  -H "Authorization: Bearer YOUR_CRON_SECRET"
```

**Expected Response:**
```json
{
  "status": "success",
  "timestamp": "2025-11-07T05:00:00",
  "scraped": 15,
  "processed": 10,
  "skipped": 5,
  "postponed": 2
}
```

### Test Postponement Checker:

```bash
curl -X POST https://stc-tender-platform.onrender.com/api/cron/check-postponements \
  -H "Authorization: Bearer YOUR_CRON_SECRET"
```

---

## 📊 What Each Job Does

### **Weekly Sunday Scraper** (`/api/cron/scrape-weekly`):

1. ✅ Scrapes all 4 categories from CAPT
2. ✅ Processes with AI (summaries, extraction)
3. ✅ Detects postponements
4. ✅ Generates embeddings
5. ✅ Stores in database
6. ✅ Returns statistics

**Duration**: ~5-10 minutes

---

### **Daily Postponement Check** (`/api/cron/check-postponements`):

1. ✅ Quick scrape of closing tenders
2. ✅ Checks for deadline changes
3. ✅ Updates postponement flags
4. ✅ Lightweight & fast

**Duration**: ~1-2 minutes

---

## 🕐 Time Zone Info

**Kuwait Time (AST)**: UTC+3 (no DST)

**Cron Schedule Examples:**
- `0 5 * * 0` = Sunday 5 AM UTC = Sunday 8 AM Kuwait
- `0 5 * * 1-6` = Mon-Sat 5 AM UTC = Mon-Sat 8 AM Kuwait

---

## 🔔 Monitoring

### Check Logs in Render:

1. Go to your service dashboard
2. Click **Logs** tab
3. Filter by time: Sunday morning
4. Look for:
   - `🤖 Starting weekly scrape`
   - `✅ Scraped X tenders`
   - `✅ Weekly scrape completed`

### Error Alerts:

Set up email alerts in Render:
1. Go to **Settings** → **Notifications**
2. Enable **Failed Builds** and **Service Errors**

---

## 🚀 Deployment

After setting up cron jobs, your platform will automatically:

1. **Every Sunday**: Import new tenders from Kuwait Al-Youm
2. **Every Day**: Check for postponements
3. **Send Stats**: Track success in logs
4. **Auto-Recovery**: Retry on failures

---

## 📝 Next Steps (Optional)

### Add Email Notifications:

1. Install email service (SendGrid, Mailgun)
2. Notify users when:
   - New tenders in their ministry
   - Tender postponed
   - Deadline approaching

### Add Webhook:

Post scrape results to Slack/Discord:
```python
requests.post(WEBHOOK_URL, json=result)
```

---

## ✅ Verification Checklist

- [ ] CRON_SECRET generated and added to Render
- [ ] Weekly scraper cron job created
- [ ] Daily checker cron job created (optional)
- [ ] Test endpoint with curl (successful)
- [ ] Check logs for "Starting weekly scrape" message
- [ ] Verify new tenders appear in database

---

**Your automatic scraping is now configured! 🎉**

Tenders will be automatically imported every Sunday at 8 AM Kuwait time.
