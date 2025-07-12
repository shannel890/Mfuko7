import os
from dotenv import load_dotenv
from decouple import config

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    SECURITY_PASSWORD_SALT = os.getenv('SECURITY_PASSWORD_SALT')

    # M-Pesa API Configuration
    MPESA_CONSUMER_KEY = config('MPESA_CONSUMER_KEY', default=None)
    MPESA_CONSUMER_SECRET = config('MPESA_CONSUMER_SECRET', default=None)
    MPESA_PASSKEY = config('MPESA_PASSKEY', default=None)
    MPESA_SHORTCODE = config('MPESA_SHORTCODE', default='174379')
    MPESA_PAYBILL = config('MPESA_PAYBILL', default='174379')
    MPESA_INITIATOR_PASSWORD = config('MPESA_INITIATOR_PASSWORD', default='Safaricom999!')
    MPESA_SAF_CALLBACK_URL = config('MPESA_SAF_CALLBACK_URL', default='https://example.com/callback')
    MPESA_ENVIRONMENT = config('MPESA_ENVIRONMENT', default='sandbox')

    # Mail Configuration
    MAIL_SERVER = config('MAIL_SERVER', default='smtp.mailtrap.io')
    MAIL_PORT = config('MAIL_PORT', default=2525, cast=int)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes', 'on')
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() in ('true', '1', 'yes', 'on')
    MAIL_USERNAME = config('MAIL_USERNAME',default='shannelkirui739@gmail.com')
    MAIL_PASSWORD = config('MAIL_PASSWORD',default=None)
    MAIL_DEFAULT_SENDER = config('MAIL_DEFAULT_SENDER', default='noreply@example.com')

    # Google OAuth
    GOOGLE_CLIENT_ID = config('GOOGLE_CLIENT_ID', default=None)
    GOOGLE_CLIENT_SECRET = config('GOOGLE_CLIENT_SECRET', default=None)

    # Twilio
    TWILIO_ACCOUNT_SID = config('TWILIO_ACCOUNT_SID', default=None)
    TWILIO_AUTH_TOKEN = config('TWILIO_AUTH_TOKEN', default=None)
    TWILIO_PHONE_NUMBER = config('TWILIO_PHONE_NUMBER', default=None)

    # APScheduler
    SCHEDULER_API_ENABLED = True
