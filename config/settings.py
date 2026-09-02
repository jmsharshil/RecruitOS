import os
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-dummy-key')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,recruitos-c9bga4b9d9hjc3gh.centralindia-01.azurewebsites.net,recruitos.dspe.in,victorious-plant-004ecb500.6.azurestaticapps.net,recuitosdspe-e4bbhucfc3gvhbhj.centralindia-01.azurewebsites.net', cast=Csv())

# Frontend URLs for emails and CORS
FRONTEND_URL = config('FRONTEND_URL', default='https://recruitos.jmstech.co')
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'drf_spectacular',

    # Internal apps
    'accounts',
    'clients',
    'jobs',
    'candidates',
    'notifications',
    'audit',
    'common',
    'channels',
]

AUTH_USER_MODEL = 'accounts.User'

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'audit.middleware.AuditLogMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

CONNECTION_STRING = os.environ.get('AZURE_POSTGRESQL_CONNECTIONSTRING')

if not CONNECTION_STRING:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    conn_str_params = {pair.split('=')[0]: pair.split('=')[1] for pair in CONNECTION_STRING.split(' ')}
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': conn_str_params['dbname'],
            'HOST': conn_str_params['host'],
            'USER': conn_str_params['user'],
            'PASSWORD': conn_str_params['password'],
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / config('STATIC_ROOT', default='staticfiles')
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / config('MEDIA_ROOT', default='media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'common.exceptions.custom_exception_handler'
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(hours=8000),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS':  True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'RecruitSmart ATS API',
    'DESCRIPTION': 'Multi-tenant Recruitment / Applicant Tracking System (ATS). Features role-based dashboards (Admin/Manager/Recruiter), client & job management, candidate pipeline with stages, interviews, submissions, audit trail, notifications, and CSV bulk import/export. Strict organization-level data isolation enforced.',
    'VERSION': '1.0.0',
    'SWAGGER_UI_SETTINGS': {
        'docExpansion': 'list',
        'defaultModelsExpandDepth': -1,
        'filter': True,
        'displayRequestDuration': True,
    },
    'REDOC_SETTINGS': {
        'theme': {
            'primaryColor': '#1e40af',
        }
    },
}

FRONTEND_BASE_URL = os.getenv('FRONTEND_BASE_URL', 'https://recruitos.jmstech.co')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')

# ═══════════════════════════════════════════════════════════════════════════════
# Security Headers (Production)
# ═══════════════════════════════════════════════════════════════════════════════

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ═══════════════════════════════════════════════════════════════════════════════
# Logging Configuration (Production)
# ═══════════════════════════════════════════════════════════════════════════════

if not DEBUG:
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '{levelname} {asctime} {module} {message}',
                'style': '{',
            },
        },
        'handlers': {
            'file': {
                'level': 'ERROR',
                'class': 'logging.FileHandler',
                'filename': '/home/site/wwwroot/django_errors.log',
                'formatter': 'verbose',
            },
        },
        'loggers': {
            'django': {
                'handlers': ['file'],
                'level': 'ERROR',
                'propagate': False,
            },
        },
    }
if not DEBUG:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

CSRF_TRUSTED_ORIGINS = ["https://*.azurewebsites.net", "http://localhost:5173", "http://localhost:3000", "https://app.apidog.com", "https://recruitos.dspe.in", "https://victorious-plant-004ecb500.6.azurestaticapps.net"]
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='http://localhost:5173,http://localhost:3000,https://app.apidog.com,https://recruitos.dspe.in,https://victorious-plant-004ecb500.6.azurestaticapps.net', cast=Csv())

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB

# OpenAI/Azure settings for AI resume parsing
OPENAI_API_KEY = config('OPENAI_API_KEY', default='dummy-azure-key')
AZURE_OPENAI_ENDPOINT = config('AZURE_OPENAI_ENDPOINT', default='https://your-resource.openai.azure.com/')
OPENAI_API_VERSION = config('OPENAI_API_VERSION', default='2024-10-01')

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

EMAIL_HOST = config("EMAIL_HOST_SERVER", default="smtp.office365.com")
EMAIL_PORT = config("EMAIL_HOST_PORT", default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@recruitsmart.local')
EMAIL_FROM = DEFAULT_FROM_EMAIL

# Fernet key for encrypting per-org SMTP passwords stored in DB.
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Keep this secret — rotating it requires re-saving all org SMTP passwords.
EMAIL_ENCRYPTION_KEY = config('EMAIL_ENCRYPTION_KEY', default='')

# Media files (user uploads)
USE_AZURE_MEDIA = os.environ.get("USE_AZURE_MEDIA", "0") in ("1", "true", "True")

if USE_AZURE_MEDIA:
    AZURE_ACCOUNT_NAME = os.environ["AZURE_ACCOUNT_NAME"]
    AZURE_ACCOUNT_KEY  = os.environ["AZURE_ACCOUNT_KEY"]
    AZURE_CONTAINER    = os.environ.get("AZURE_MEDIA_CONTAINER")
    AZURE_ACCOUNT_URL  = f"https://{AZURE_ACCOUNT_NAME}.blob.core.windows.net"
    AZURE_CUSTOM_DOMAIN = os.environ.get(
        "AZURE_CUSTOM_DOMAIN",
        f"{AZURE_ACCOUNT_NAME}.blob.core.windows.net",
    )
    AZURE_URL_EXPIRATION_SECS = int(os.environ.get("AZURE_URL_EXPIRATION_SECS", "3600"))
    AZURE_OVERWRITE_FILES = False

    STORAGES["default"] = {
        "BACKEND": "storages.backends.azure_storage.AzureStorage",
        "OPTIONS": {
            "account_name": AZURE_ACCOUNT_NAME,
            "account_key": AZURE_ACCOUNT_KEY,
            "azure_container": AZURE_CONTAINER,
            "overwrite_files": AZURE_OVERWRITE_FILES,
            "expiration_secs": None,
        }
    }

    WHITENOISE_USE_FINDERS = True

    MEDIA_URL = f"https://{AZURE_CUSTOM_DOMAIN}/{AZURE_CONTAINER}/"
else:
    MEDIA_URL  = "/media/"
    MEDIA_ROOT = os.path.join(BASE_DIR, "media")
GOOGLE_OAUTH_CLIENT_ID = config('GOOGLE_OAUTH_CLIENT_ID', default='543573978646-hgopbbdj7gvl3uvuatf5no529shg1q8r.apps.googleusercontent.com')
GOOGLE_OAUTH_CLIENT_SECRET = config('GOOGLE_OAUTH_CLIENT_SECRET', default='')
