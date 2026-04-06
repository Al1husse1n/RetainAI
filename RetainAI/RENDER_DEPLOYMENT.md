# Render Deployment Instructions

## Prerequisites
1. Create a Render.com account
2. Connect your GitHub repository to Render
3. Ensure your repository has all the generated files
4. Get a Google AI API key from [Google AI Studio](https://makersuite.google.com/app/apikey)

## Files Generated
- `Dockerfile`: Multi-stage build for Django app
- `docker-compose.yml`: Defines web service (uses Google Gemini API directly)
- `requirements.txt`: Updated with gunicorn, whitenoise, langchain-google-genai, and python-dotenv
- `render.yaml`: Render configuration (if needed for advanced setup)

## Settings.py Changes Required

Update your `RetainAI/settings.py` for production:

```python
# Add these imports at the top
import os

# Update DEBUG
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# Update ALLOWED_HOSTS
ALLOWED_HOSTS = ['*']  # Or specify your Render domain

# Add STATIC_ROOT
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Add whitenoise middleware (after SecurityMiddleware)
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Add this line
    # ... rest of your middleware
]

# Update SECRET_KEY
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'fallback-key-change-in-production')
```

## Environment Variables
Render will automatically set:
- `PORT`: The port your app should listen on (for Docker deployments)

Set these in Render dashboard:
- `GOOGLE_API_KEY`: Your primary Google AI API key (required for Gemini)
- `GOOGLE_API_KEY_BACKUP_1`: Optional backup Google AI API key to use if the primary key has reached quota.
- `GOOGLE_API_KEY_BACKUP_2`: Optional second backup Google AI API key to use if the first key fails.
- `DJANGO_SECRET_KEY`: A secure random key
- `DEBUG`: False

## Deployment Steps

### Option 1: Docker Deployment (Recommended)
1. In Render dashboard, create a new **Web Service**
2. Connect your GitHub repo
3. Select **Docker** as the runtime
4. Set the following environment variables:
   - `GOOGLE_API_KEY` = your Google AI API key
   - `DJANGO_SECRET_KEY` = a secure random string
   - `DEBUG` = False
5. Deploy - Render will build using your Dockerfile

### Option 2: Python Native Deployment
If you prefer not to use Docker:
1. In Render dashboard, create a new **Web Service**
2. Select **Python** as the runtime
3. Set build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
4. Set start command: `gunicorn RetainAI.wsgi:application --bind 0.0.0.0:$PORT`
5. Set environment variables as above

## Model Note
No model pulling needed - Google Gemini API is used directly, so deployments are fast.

## Troubleshooting
- If deployment fails, check the build logs for missing dependencies
- Ensure your Google AI API key is valid and has quota
- For Docker deployments, verify your Dockerfile works locally first
- Render's free tier has usage limits, monitor your service