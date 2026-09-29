# -*- coding: utf-8 -*-
import os

TIME_ZONE = 'America/Chicago'

LANGUAGE_CODE = 'en-us'

SITE_ID = 1

USE_I18N = False


SECRET_KEY = 'j&7h+dv&l12399ts8u$n!xpu0et509&5rec#6f84m*o$@!0a^5'

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.load_template_source',
)

TEMPLATE_CONTEXT_PROCESSORS = (
    "django.contrib.auth.context_processors.auth",
    "django.core.context_processors.debug",
    "django.core.context_processors.i18n",
    "django.core.context_processors.media",
    "django.core.context_processors.static",
    "django.core.context_processors.request",
    "django.contrib.messages.context_processors.messages",

)


AUTHENTICATION_BACKENDS = (

    'emailuser.auth.EmailAuthBackend',
    'django.contrib.auth.backends.ModelBackend',

)

AUTH_PROFILE_MODULE = 'flash.profile'


TWITTER_CONSUMER_KEY = ''
TWITTER_CONSUMER_SECRET = ''
FACEBOOK_APP_ID = ''
FACEBOOK_API_SECRET = ''

LOGIN_URL          = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGIN_ERROR_URL    = '/'

MIDDLEWARE_CLASSES = (
    #'django.middleware.cache.UpdateCacheMiddleware',
    'django.middleware.common.CommonMiddleware',
   # 'django.middleware.cache.FetchFromCacheMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.contrib.flatpages.middleware.FlatpageFallbackMiddleware',
)

ROOT_URLCONF = 'xxxflash.urls'

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.sites',
    'django.contrib.flatpages',
    'flash',    
    'baner',
    'emailuser', 
)

CONTENT_TYPES = ['x-shockwave-flash',]
ACCOUNT_ACTIVATION_DAYS = 7
#LOGIN_REDIRECT_URL = '/profiles/edit/'
APPEND_SLASH=True

ADMIN_TOOLS_INDEX_DASHBOARD = 'dashboard.CustomIndexDashboard'

FILE_UPLOAD_MAX_MEMORY_SIZE = 20480000

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler'
        },
        'console':{
            'level':'ERROR',
            'class':'logging.StreamHandler'
        },
    },
    'loggers': {
        'django.request': {
            'handlers': [ 'console', 'mail_admins', ],
            'level': 'ERROR',
            'propagate': True,
        },
    }
}

COMMENTS_PER_PAGE = 20
GAMES_PER_PAGE = 15
BEST_GAMES_COUNT = 20
INDEX_ORDER_BY  = ["-publication_date", "-rate", "-views", "-id"]
SITE_URL = "http://localhost/"
_PAGE_LINKS = 10


ABS_ROOT = os.path.abspath(os.path.dirname(__file__))

# Loading beeline and megafon
try:
    m = open('%s/../data/megafon.txt' % ABS_ROOT)
    MEGAFON = m.read().strip()
    m.close()
except IOError:
    MEGAFON = "78.25.120.0/22 85.26.184.0/24 85.26.234.0/23 83.149.48.0/25 83.149.44.0/23 83.149.21.0/24 85.26.164.0/23 85.26.232.0/23 85.26.183.0/24 85.26.231.0/25 85.26.241.0/24 83.149.35.0/24 85.26.186.0/24 46.229.140.0/24 83.149.38.0/24 83.149.34.128/25 83.149.52.0/22 193.201.231.2/32 83.149.9.72/32 83.149.8.38/32 83.149.8.126/32 83.149.9.120/32 83.149.9.80/32 83.149.9.52/32 83.149.8.154/32 83.149.9.216/32 83.149.9.10/32 83.149.9.78/32 83.149.9.132/32 83.149.9.190/32 83.149.8.68/32 83.149.9.64/32 83.149.9.36/32 83.149.9.4/32 83.149.9.46/32 83.149.8.170/32 83.149.8.16/32 83.149.9.152/32 83.149.9.68/32 83.149.8.216/32 83.149.9.82/32 83.149.8.56/32 83.149.8.214/32 83.149.9.184/32 83.149.8.118/32 83.149.9.136/32 83.149.9.84/32 83.149.8.82/32 83.149.8.124/32 83.149.9.114/32 83.149.8.202/32 83.149.9.142/32 83.149.8.90/32 83.149.9.62/32 83.149.8.86/32 83.149.9.70/32 83.149.8.70/32 83.149.8.146/32 83.149.8.212/32 83.149.8.52/32 83.149.9.166/32 83.149.9.200/32 83.149.8.152/32 83.149.9.212/32 83.149.8.0/32 83.149.8.50/32 83.149.8.64/32 83.149.8.92/32 83.149.9.86/32 83.149.9.222/32 83.149.9.126/32 83.149.9.124/32 83.149.9.218/32 83.149.8.36/32 83.149.9.56/32 83.149.9.2/32 83.149.8.178/32 83.149.9.156/32 83.149.9.178/32 83.149.9.196/32 83.149.9.210/32 83.149.9.100/32 83.149.9.202/32 83.149.9.92/32 83.149.8.132/32 83.149.8.210/32 83.149.9.32/32 83.149.9.154/32 83.149.8.2/32 83.149.8.162/32 83.149.8.142/32 83.149.8.140/32 83.149.9.12/32 83.149.8.174/32 83.149.8.22/32"

try:
    m = open('%s/../data/beeline.txt' % ABS_ROOT)
    BEELINE = m.read().strip()
    m.close()
except IOError:
    BEELINE = "217.118.81.0/24 217.118.79.0/24 85.115.248.0/24 217.118.78.0/24 217.118.93.0/24 83.220.238.0/24 217.118.83.0/24 83.220.237.0/24 217.118.64.32/27 217.118.90.0/24 217.118.95.0/25 83.220.236.128/25 83.220.239.0/25 217.118.95.128/25 217.118.91.64/26 83.220.236.64/26 83.220.239.128/26 31.13.144.16/28 31.13.144.32/28 85.115.243.32/27 217.118.66.0/24 83.220.236.32/27 83.220.239.192/27 31.13.144.48/29 31.13.144.8/29 85.115.224.128/27 83.220.236.16/28 83.220.239.224/28 31.13.144.56/30 31.13.144.4/30 85.115.248.192/27 85.115.224.200/29 85.115.224.208/29 217.118.91.112/29 83.220.236.8/29 83.220.239.240/29 31.13.144.60/31 31.13.144.2/31 85.115.248.224/28 85.115.224.196/30 217.118.91.120/30 83.220.236.4/30 85.115.224.216/30 85.115.248.240/29 31.13.144.62/32 83.220.239.248/30 217.118.91.124/31 85.115.224.194/31 85.115.224.220/31 "

BEELINE = BEELINE.split(' ')
MEGAFON = MEGAFON.split(' ')
EDGE_NETS = MEGAFON + BEELINE 

# 
SPHINX_API_VERSION = 0x113
THUMB_WIDTH = 350
THUMB_HEIGHT = 350

SMALL_THUMB_WIDTH = 50
SMALL_THUMB_HEIGHT = 50

DEFAULT_WIDTH = 700

RANDOM_FLASH_COUNT = 5
BEST_FLASH_COUNT = 5

try:
    from local_settings import *
except ImportError:
    pass
