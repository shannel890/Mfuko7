from flask import Flask
from app.extensions import login_manager,migrate
from app.extensions import db, babel, mail, csrf, scheduler, oauth
from .models import User, Role
from app.routes import main
from app.auth.routes import auth
import os
import uuid
from app.extensions import mail
from werkzeug.security import generate_password_hash
import logging
from app.job import notify_due_payments
from app.mpesa.mpesa_api import MpesaAPI
from decouple import config 
from dotenv import load_dotenv

load_dotenv()



logging.basicConfig(
    level=logging.DEBUG,  # or INFO to reduce noise
    format='%(asctime)s [%(levelname)s] %(message)s',
)


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')  
    app.config['SQLALCHEMY_ENGINES'] = {"default": 'sqlite:///app.db'}
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECURITY_REGISTERABLE'] = True
    app.config['SECURITY_SEND_REGISTER_EMAIL'] = False
    app.config['SECURITY_USE_REGISTER_V2'] = True
    app.config['SECURITY_RECOVERABLE'] = True
    app.config['SECURITY_CHANGEABLE'] =True
    app.config['SECURITY_CONFIRMABLE'] = False
    app.config['SECURITY_FRESHNESS_GRACE_PERIOD'] = 300
    app.config['MAIL_SERVER'] = 'MAIL_SERVER'
    app.config['MAIL_PORT'] = 'MAIL_PORT'
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('shannelkirui739@gmail.com')
    app.config['MPESA_CONSUMER_KEY'] = config('MPESA_CONSUMER_KEY')
    app.config['MPESA_CONSUMER_SECRET'] = config('MPESA_CONSUMER_SECRET')
    app.config['MPESA_SHORTCODE'] = config('MPESA_SHORTCODE')
    app.config['MPESA_PASSKEY'] = config('MPESA_PASSKEY')
    app.config['MPESA_CALLBACK_URL'] = config('MPESA_CALLBACK_URL', default='https://example.com/callback')
    app.config['MPESA_ENVIRONMENT'] = config('MPESA_ENVIRONMENT', 'sandbox')
    app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
    app.config['GOOGLE_CLIENT_SECRET'] = os.getenv('GOOGLE_CLIENT_SECRET')

    
    db.init_app(app)
    babel.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    scheduler.init_app(app)
    scheduler.start()
    oauth.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    scheduler.add_job(
        id='notify_due_payments',
        func=notify_due_payments,
        trigger='cron',
        hour=8,
        replace_existing=True
    )

    oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)


    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    app.register_blueprint(main)
    app.register_blueprint(auth)

    with app.app_context():
        # ✅ Create MpesaAPI instance inside app context
        app.mpesa_api = MpesaAPI()

        print("MPESA_CONSUMER_KEY:", app.config.get('MPESA_CONSUMER_KEY'))
        print("MPESA_SHORTCODE:", app.config.get('MPESA_SHORTCODE'))
        
        db.create_all()

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