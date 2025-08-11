# Railway Deployment Guide

## Prerequisites

1. Railway account
2. Railway CLI installed (optional)
3. Git repository

## Deployment Steps

### 1. Database Setup

Your PostgreSQL database is already created on Railway:
```
postgresql://postgres:YOJLwGeQgCBnXOSgvAbimrXYqotllvRI@hopper.proxy.rlwy.net:15254/railway
```

### 2. Initialize Database Tables

Run locally first to create tables:
```bash
cd accountant-ai
python init_db.py
```

### 3. Set Environment Variables on Railway

Go to your Railway project settings and add these environment variables:

```env
# Application
APP_NAME=AccountantAI
APP_ENV=production
DEBUG=False
SECRET_KEY=<generate-a-secure-key>

# Database (already set by Railway)
DATABASE_URL=<automatically-set-by-railway>

# Redis (already set by Railway)
REDIS_URL=<automatically-set-by-railway>

# Gmail API
GMAIL_CLIENT_ID=<your-gmail-client-id>
GMAIL_CLIENT_SECRET=<your-gmail-client-secret>
GMAIL_REDIRECT_URI=https://<your-app>.up.railway.app/auth/gmail/callback

# OpenAI
OPENAI_API_KEY=<your-openai-api-key>
OPENAI_MODEL=gpt-4-vision-preview

# Folio.no
FOLIO_SESSION_COOKIE=s%3AhywBA5PjLjSjoMh2idouX2ro6iPvYDbF.FyD5do37dqCTmskr5rWQW%2Bmb%2BVIeFczYs7BDLHrCiRg
FOLIO_ORG_NUMBER=932951460

# Fiken
FIKEN_CLIENT_ID=G6hCCHpYnXzy4QZE25534234754512587
FIKEN_CLIENT_SECRET=ca1251da-fa0b-4239-8430-bac9865c7780
FIKEN_REDIRECT_URI=https://<your-app>.up.railway.app/auth/fiken/callback
FIKEN_API_URL=https://api.fiken.no/api/v2
FIKEN_COMPANY_ID=<your-fiken-company-id>

# File storage
UPLOAD_FOLDER=/app/uploads
MAX_FILE_SIZE=10485760

# Logging
LOG_LEVEL=INFO
```

### 4. Update OAuth Redirect URLs

Update your OAuth providers with Railway URLs:

#### Gmail (Google Cloud Console):
- Add: `https://<your-app>.up.railway.app/auth/gmail/callback`

#### Fiken:
- Add: `https://<your-app>.up.railway.app/auth/fiken/callback`

### 5. Deploy

#### Option A: Via GitHub
1. Push your code to GitHub
2. Connect Railway to your GitHub repo
3. Railway will auto-deploy on push

#### Option B: Via Railway CLI
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link to project
railway link

# Deploy
railway up
```

### 6. Post-Deployment

1. Visit `https://<your-app>.up.railway.app/health` to verify deployment
2. Authenticate services:
   - `https://<your-app>.up.railway.app/auth/gmail`
   - `https://<your-app>.up.railway.app/auth/fiken`

## Important Notes

1. **Session Cookie**: Folio session cookies expire. Update the environment variable when needed.

2. **File Storage**: Railway ephemeral storage resets on redeploy. Consider using cloud storage (S3, Cloudinary) for production.

3. **Secrets**: Generate a secure SECRET_KEY:
   ```python
   import secrets
   print(secrets.token_urlsafe(32))
   ```

4. **Monitoring**: Check Railway logs for any errors:
   ```bash
   railway logs
   ```

## Troubleshooting

### Database Connection Issues
- Verify DATABASE_URL is set correctly
- Check Railway PostgreSQL plugin is attached

### OAuth Redirect Errors
- Ensure redirect URLs match exactly
- Update both local and production URLs

### File Upload Issues
- Check UPLOAD_FOLDER exists
- Consider implementing cloud storage for persistence