import os
import uuid
import logging
from flask import Flask
from decouple import config
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from twilio.rest import Client
from datetime import datetime
from app.extensions import db, babel, mail, csrf, scheduler, oauth, login_manager, migrate
from app.models import User, Role
from app.routes import main
from app.auth.routes import auth
from app.job import rent_due_reminders, overdue_notifications
from app.mpesa.mpesa_api import MpesaAPI

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
)

def create_app():
    app = Flask(__name__)

    # --- Basic config
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # --- Flask-Security config
    app.config['SECURITY_REGISTERABLE'] = True
    app.config['SECURITY_SEND_REGISTER_EMAIL'] = False
    app.config['SECURITY_USE_REGISTER_V2'] = True
    app.config['SECURITY_RECOVERABLE'] = True
    app.config['SECURITY_CHANGEABLE'] = True
    app.config['SECURITY_CONFIRMABLE'] = False
    app.config['SECURITY_FRESHNESS_GRACE_PERIOD'] = 300

    # --- Mail config
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'no-reply@example.com')

    # --- M-Pesa config
    app.config['MPESA_CONSUMER_KEY'] = config('MPESA_CONSUMER_KEY')
    app.config['MPESA_CONSUMER_SECRET'] = config('MPESA_CONSUMER_SECRET')
    app.config['MPESA_SHORTCODE'] = config('MPESA_SHORTCODE')
    app.config['MPESA_PASSKEY'] = config('MPESA_PASSKEY')
    app.config['MPESA_CALLBACK_URL'] = config('MPESA_CALLBACK_URL', default='https://example.com/callback')
    app.config['MPESA_ENVIRONMENT'] = config('MPESA_ENVIRONMENT', default='sandbox')

    # --- Google OAuth
    app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
    app.config['GOOGLE_CLIENT_SECRET'] = os.getenv('GOOGLE_CLIENT_SECRET')

    # --- Twilio
    app.config['TWILIO_ACCOUNT_SID'] = config('TWILIO_ACCOUNT_SID')
    app.config['TWILIO_AUTH_TOKEN'] = config('TWILIO_AUTH_TOKEN')
    app.config['TWILIO_PHONE_NUMBER'] = config('TWILIO_PHONE_NUMBER')

    # --- Init extensions
    db.init_app(app)
    babel.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    oauth.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    # --- Scheduler jobs
    scheduler.init_app(app)
    scheduler.start()
    scheduler.add_job(
        id='rent_due_reminders',
        func=rent_due_reminders,
        trigger='cron',
        hour=9
    )
    scheduler.add_job(
        id='overdue_notifications',
        func=overdue_notifications,
        trigger='cron',
        hour=10
    )

    # --- Twilio client setup
    global twilio_client
    twilio_client = Client(
        app.config['TWILIO_ACCOUNT_SID'],
        app.config['TWILIO_AUTH_TOKEN']
    )

    # --- Google OAuth registration
    oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )

    # --- User loader
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # --- Register Blueprints
    app.register_blueprint(main)
    app.register_blueprint(auth)

    @app.context_processor
    def inject_globals():
        return {'datetime': datetime}
    # --- App context logic
    with app.app_context():
        app.mpesa_api = MpesaAPI()

        db.create_all()

        # Setup landlord role & default user (optional)
        landlord_role = Role.query.filter_by(name='landlord').first()
        if not landlord_role:
            landlord_role = Role(name='landlord')
            db.session.add(landlord_role)
            db.session.commit()

        landlord_user = User.query.filter_by(email='shannel@gmail.com').first()
        if not landlord_user:
            landlord_user = User(
                email='shannel@gmail.com',
                password=generate_password_hash('shannel254'),
                first_name='shannel',
                last_name='kirui',
                fs_uniquifier=str(uuid.uuid4()),
                active=True,
                roles=[landlord_role]
            )
            db.session.add(landlord_user)
        db.session.commit()

    return app
