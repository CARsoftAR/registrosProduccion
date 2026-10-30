"""
Django settings for Auditoría y Control de Producción ABBAMAT.
Módulo 100% independiente y autónomo para control de planta y tiempos de taller.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Cargar variables de entorno
load_dotenv(BASE_DIR / '.env')

# Clave secreta
SECRET_KEY = os.getenv('SECRET_KEY', 'abbamat-prod-control-audit-secret-key-2026-isolated')

# Modo depuración
DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Aplicación dedicada de Control y Auditoría de Producción
    'control_produccion',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'control_produccion.context_processors.fechas_auditoria_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Base de datos local SQLite para configuración y estado de auditoría
# Aislada completamente de cualquier sistema de RRHH o fichadas
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Configuración de conexión SOLO LECTURA a base de datos del ERP
ERP_DB_CONFIG = {
    'HOST': os.getenv('ERP_DB_HOST', '192.168.88.12'),
    'NAME': os.getenv('ERP_DB_NAME', 'EqualRP_Prod_Master'),
    'USER': os.getenv('ERP_DB_USER', 'tablero'),
    'PASSWORD': os.getenv('ERP_DB_PASS', 'tablero2019'),
    'DRIVER': os.getenv('ERP_DB_DRIVER', 'SQL Server Native Client 11.0'),
}

# Parámetros por defecto de taller (estáticos en backend: 8,5 hs, 07:00 a 16:00)
JORNADA_TEORICA_HORAS = 8.5
MINUTOS_TEORICOS_JORNADA = 510.0
TOLERANCIA_BACHE_MINUTOS = 15
HORA_INICIO_TURNO = '07:00'
HORA_FIN_TURNO = '16:00'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internacionalización y Zona Horaria
LANGUAGE_CODE = 'es-ar'
TIME_ZONE = 'America/Argentina/Buenos_Aires'
USE_I18N = True
USE_TZ = False

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
