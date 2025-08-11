# 🚀 Quick Deployment Guide for AccountantAI

## Your Railway Setup

You have:
- ✅ PostgreSQL database on Railway
- ✅ Redis instance on Railway
- ✅ Folio.no credentials
- ✅ Fiken credentials

## What You Still Need:

### 1. Gmail API Credentials
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select existing
3. Enable Gmail API
4. Create OAuth 2.0 credentials
5. Add redirect URIs:
   - `http://localhost:8000/auth/gmail/callback` (for local testing)
   - `https://YOUR-APP.up.railway.app/auth/gmail/callback` (for production)

### 2. OpenAI API Key
1. Go to [OpenAI Platform](https://platform.openai.com/api-keys)
2. Create a new API key
3. Copy the key (you won't see it again!)

### 3. Fiken Company ID
1. Log in to Fiken
2. Go to Innstillinger → Firmaopplysninger
3. Find your Company ID

## Local Setup (First Time)

```bash
cd accountant-ai

# Run setup script
./setup.sh

# Or manually:
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python init_db.py
```

## Deploy to Railway

### Method 1: GitHub Integration (Recommended)

1. Push to GitHub:
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin YOUR_GITHUB_REPO
git push -u origin main
```

2. In Railway:
   - New Project → Deploy from GitHub repo
   - Select your repository
   - Railway auto-deploys on every push

### Method 2: Railway CLI

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway link
railway up
```

## Environment Variables for Railway

Copy these to Railway dashboard (Settings → Variables):

```env
# App
APP_NAME=AccountantAI
APP_ENV=production
DEBUG=False
SECRET_KEY=GENERATE-USING-PYTHON-SECRETS

# APIs
GMAIL_CLIENT_ID=your-value
GMAIL_CLIENT_SECRET=your-value
GMAIL_REDIRECT_URI=https://YOUR-APP.up.railway.app/auth/gmail/callback

OPENAI_API_KEY=your-openai-key
OPENAI_MODEL=gpt-4-vision-preview

# Folio.no (you have these)
FOLIO_SESSION_COOKIE=s%3AhywBA5PjLjSjoMh2idouX2ro6iPvYDbF.FyD5do37dqCTmskr5rWQW%2Bmb%2BVIeFczYs7BDLHrCiRg
FOLIO_ORG_NUMBER=932951460

# Fiken (you have these)
FIKEN_CLIENT_ID=G6hCCHpYnXzy4QZE25534234754512587
FIKEN_CLIENT_SECRET=ca1251da-fa0b-4239-8430-bac9865c7780
FIKEN_REDIRECT_URI=https://YOUR-APP.up.railway.app/auth/fiken/callback
FIKEN_COMPANY_ID=your-company-id

# Settings
RECEIPT_EMAIL_FILTER=invoice,receipt,faktura,kvittering
UPLOAD_FOLDER=/app/uploads
MAX_FILE_SIZE=10485760
LOG_LEVEL=INFO
```

## Generate Secret Key

```python
import secrets
print(secrets.token_urlsafe(32))
```

## After Deployment

1. Get your Railway app URL from the dashboard
2. Update OAuth redirect URLs:
   - Google Cloud Console: Add Railway URL
   - Fiken: Add Railway URL
3. Visit `https://YOUR-APP.up.railway.app/health` to verify
4. Authenticate services:
   - `/auth/gmail`
   - `/auth/fiken`

## Testing Locally First

```bash
source venv/bin/activate
uvicorn src.api.main:app --reload
```

Visit http://localhost:8000/docs for API documentation

## Important Notes

⚠️ **Folio Session Cookie**: Expires periodically. Update in Railway variables when needed.

⚠️ **File Storage**: Consider adding AWS S3 or Cloudinary for permanent file storage in production.

⚠️ **Database**: Your Railway PostgreSQL is already configured and ready!