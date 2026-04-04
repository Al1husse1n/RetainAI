# Railway Deployment Instructions

## Prerequisites
1. Create a Railway.app account
2. Connect your GitHub repository to Railway
3. Ensure your repository has all the generated files

## Files Generated
- `Dockerfile`: Multi-stage build for Django app
- `docker-compose.yml`: Defines ollama and web services
- `requirements.txt`: Updated with gunicorn and whitenoise
- `railway.json`: Railway configuration

## Settings.py Changes Required

Update your `RetainAI/settings.py` for production:

```python
# Add these imports at the top
import os

# Update DEBUG
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# Update ALLOWED_HOSTS
ALLOWED_HOSTS = ['*']  # Or specify your Railway domain

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
Railway will automatically set:
- `PORT`: The port your app should listen on

Set these in Railway dashboard:
- `DJANGO_SECRET_KEY`: A secure random key
- `DEBUG`: False (already set in docker-compose.yml)

## Model Pulling Note
Since Ollama runs in Docker, the first deployment may take several minutes to pull the `llama3.2:3b` model. Subsequent deployments will be faster as the model is cached in the named volume.

## Deployment Steps
1. Push all changes to your GitHub repository
2. In Railway dashboard, create a new project from your GitHub repo
3. Railway will automatically detect the `railway.json` and use Docker Compose
4. The deployment will build and start both services
5. Once deployed, your app will be available at the Railway-provided URL

## Troubleshooting
- If the first deployment times out, it's likely the Ollama model pull. Wait a bit longer.
- Check Railway logs for any build or runtime errors
- Ensure all environment variables are set correctly