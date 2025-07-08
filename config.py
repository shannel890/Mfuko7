import os
from dotenv import load_dotenv
from decouple import config
load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    SECURITY_PASSWORD_SALT=os.getenv('SECURITY_PASSWORD_SALT')
    MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER')
    # M-Pesa API Configuration
    MPESA_CONSUMER_KEY = config('MPESA_CONSUMER_KEY', default=None)
    MPESA_CONSUMER_SECRET = config('MPESA_CONSUMER_SECRET', default=None)
    MPESA_PASSKEY = config('MPESA_PASSKEY', default=None) # For STK Push
    MPESA_PAYBILL = config('MPESA_PAYBILL', default='174379') # Daraja test till number as default
    MPESA_INITIATOR_PASSWORD = config('MPESA_INITIATOR_PASSWORD', default='Safaricom999!') # Daraja test initiator password as default
    MPESA_SAF_CALLBACK_URL = config('MPESA_SAF_CALLBACK_URL', default=None) # Crucial for M-Pesa callbacks
    MPESA_ENVIRONMENT = config('MPESA_ENVIRONMENT')
    MPESA_SHORTCODE = config('MPESA_SHORTCODE')
    SCHEDULER_API_ENABLED = True
    MAIL_SERVER = config('MAIL_SERVER', 'smtp.mailtrap.io') # Or your actual SMTP server
    MAIL_PORT = config('MAIL_PORT', 2525, cast=int)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes', 'on')                                                                      
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() in ('true', '1', 'yes', 'on')
    MAIL_USERNAME = config('MAIL_USERNAME')
    MAIL_PASSWORD = config('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = config('MAIL_DEFAULT_SENDER')
    GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = config("GOOGLE_CLIENT_SECRET")
