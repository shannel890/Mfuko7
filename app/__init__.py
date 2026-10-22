import os
import logging
import secrets
import hmac
import click
from flask import Flask, request, jsonify, current_app
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

from app.extensions import db, babel, mail, csrf, oauth, login_manager, migrate, init_db_manager
from app.models import User, Role
from app.routes import main, PUBLIC_SEO_PATHS
from app.auth.routes import auth
from app.mpesa.mpesa_api import MpesaAPI
from app.ai.routes import ai

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
)

def create_app():
    app = Flask(__name__)
    public_site_url = (
        os.getenv('PUBLIC_SITE_URL')
        or os.getenv('VERCEL_PROJECT_PRODUCTION_URL')
        or 'https://www.propertypaytrack.com'
    )
    if not public_site_url.startswith(('https://', 'http://')):
        public_site_url = f'https://{public_site_url}'
    app.config['PUBLIC_SITE_URL'] = public_site_url.rstrip('/')
    app.config['VERCEL_ENVIRONMENT'] = os.getenv('VERCEL_ENV')
    # --- Basic config
    app.config['DEBUG'] = os.getenv('FLASK_DEBUG', '0') == '1'
    app.config['HOST'] = os.getenv('HOST', '127.0.0.1')
    app.config['PORT'] = int(os.getenv('PORT', 5000))
    environment = os.getenv('APP_ENV', os.getenv('FLASK_ENV', 'development'))
    app.config['APP_ENV'] = environment
    secret_key = os.getenv('SECRET_KEY')
    if not secret_key:
        if environment == 'production' or os.getenv('VERCEL'):
            raise RuntimeError('SECRET_KEY must be configured in production.')
        secret_key = secrets.token_urlsafe(48)
    app.config['SECRET_KEY'] = secret_key
    db_url = os.getenv('DATABASE_URL')

    # A local checkout works without cloud credentials. Production deployments
    # must still provide an explicit, persistent database connection.
    if not db_url:
        if os.getenv('VERCEL') or environment == 'production':
            raise RuntimeError('DATABASE_URL must be configured in production.')
        local_database = BASE_DIR / 'instance' / 'mfuko.db'
        local_database.parent.mkdir(exist_ok=True)
        db_url = f'sqlite:///{local_database}'

    # Resolve relative SQLite URLs from the project root and ensure their
    # parent directory exists. This makes DATABASE_URL=sqlite:///instance/mfuko.db
    # work on a new local checkout.
    if db_url.startswith('sqlite:///'):
        sqlite_path = Path(db_url.removeprefix('sqlite:///'))
        if sqlite_path != Path(':memory:'):
            if not sqlite_path.is_absolute():
                sqlite_path = BASE_DIR / sqlite_path
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f'sqlite:///{sqlite_path}'

    # sslmode is a PostgreSQL option and breaks SQLite URLs.
    if db_url.startswith(('postgres://', 'postgresql://', 'postgresql+psycopg2://')) and 'sslmode=' not in db_url:
        separator = "&" if "?" in db_url else "?"
        db_url += f"{separator}sslmode=require"

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # --- Flask-Security config
    app.config.update({
        'SECURITY_REGISTERABLE': True,
        'SECURITY_SEND_REGISTER_EMAIL': False,
        'SECURITY_USE_REGISTER_V2': True,
        'SECURITY_RECOVERABLE': True,
        'SECURITY_CHANGEABLE': True,
        'SECURITY_CONFIRMABLE': False,
        'SECURITY_FRESHNESS_GRACE_PERIOD': 300,
    })

    # --- Mail config
    app.config.update({
        'MAIL_SERVER': os.getenv('MAIL_SERVER'),
        'MAIL_PORT': int(os.getenv('MAIL_PORT', 587)),
        'MAIL_USE_TLS': True,
        'MAIL_USERNAME': os.getenv('MAIL_USERNAME'),
        'MAIL_PASSWORD': os.getenv('MAIL_PASSWORD'),
        'MAIL_DEFAULT_SENDER': os.getenv('MAIL_DEFAULT_SENDER'),
    })

    # --- M-Pesa config
    app.config.update({
        'MPESA_CONSUMER_KEY': os.getenv('MPESA_CONSUMER_KEY'),
        'MPESA_CONSUMER_SECRET': os.getenv('MPESA_CONSUMER_SECRET'),
        'MPESA_SHORTCODE': os.getenv('MPESA_SHORTCODE'),
        'MPESA_PASSKEY': os.getenv('MPESA_PASSKEY'),
        'MPESA_CALLBACK_URL': os.getenv('MPESA_CALLBACK_URL'),
        'MPESA_ENVIRONMENT': os.getenv('MPESA_ENVIRONMENT', 'sandbox'),
    })

    # --- Google OAuth config
    app.config.update({
        'GOOGLE_CLIENT_ID': os.getenv('GOOGLE_CLIENT_ID'),
        'GOOGLE_CLIENT_SECRET': os.getenv('GOOGLE_CLIENT_SECRET'),
    })

    # --- Twilio config
    app.config.update({
        'TWILIO_ACCOUNT_SID': os.getenv('TWILIO_ACCOUNT_SID'),
        'TWILIO_AUTH_TOKEN': os.getenv('TWILIO_AUTH_TOKEN'),
        'TWILIO_PHONE_NUMBER': os.getenv('TWILIO_PHONE_NUMBER'),
        'CRON_SECRET': os.getenv('CRON_SECRET'),
    })
    if (environment == 'production' or os.getenv('VERCEL')) and not app.config['CRON_SECRET']:
        raise RuntimeError('CRON_SECRET must be configured for production scheduled notifications.')

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

    # Recurring work is invoked by an external cron service.

    # --- OAuth registration
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

    # --- Register blueprints
    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(ai)

    @app.after_request
    def set_robots_response_header(response):
        endpoint = request.endpoint
        if endpoint in {'static', 'main.robots_txt', 'main.sitemap_xml'}:
            return response

        indexable = (
            endpoint in PUBLIC_SEO_PATHS
            and 200 <= response.status_code < 300
            and app.config['VERCEL_ENVIRONMENT'] in (None, 'production')
        )
        canonical_redirect = (
            endpoint == 'main.legacy_landing_page'
            and response.status_code in (301, 308)
        )
        if not indexable and not canonical_redirect:
            response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response

    @app.cli.command('create-admin')
    @click.option('--email', prompt=True, help='Email for the initial administrator.')
    def create_admin_command(email):
        """Provision the first administrator using a terminal password prompt."""
        from getpass import getpass
        from werkzeug.security import generate_password_hash

        email = email.strip().lower()
        if not email or '@' not in email:
            raise click.ClickException('A valid administrator email is required.')
        password = getpass('Administrator password: ')
        confirmation = getpass('Confirm administrator password: ')
        if len(password) < 12 or password != confirmation:
            raise click.ClickException('Passwords must match and be at least 12 characters long.')
        existing = User.query.filter(db.func.lower(User.email) == email).first()
        if existing:
            if existing.has_role('admin'):
                click.echo('Administrator account already exists; no changes made.')
                return
            raise click.ClickException('That account already exists without administrator rights; no changes made.')
        role = Role.query.filter_by(name='admin').first()
        if role is None:
            role = Role(name='admin', description='Administrator')
            db.session.add(role)
            db.session.flush()
        user = User(
            email=email,
            password=generate_password_hash(password),
            first_name='Administrator',
            last_name='',
            fs_uniquifier=secrets.token_urlsafe(32),
            active=True,
            role='admin',
            roles=[role],
        )
        db.session.add(user)
        db.session.commit()
        click.echo('Administrator account created.')

    @app.get('/internal/cron/rent-notifications')
    def run_rent_notification_jobs():
        cron_secret = app.config.get('CRON_SECRET')
        supplied_secret = request.headers.get('Authorization', '')
        if not cron_secret:
            current_app.logger.error('CRON_SECRET is not configured; cron request rejected.')
            return jsonify(error='Cron endpoint is not configured.'), 503
        if not hmac.compare_digest(supplied_secret, f'Bearer {cron_secret}'):
            return jsonify(error='Unauthorized.'), 401
        from app.job import rent_due_reminders, overdue_notifications
        return jsonify(results={
            'rent_due_reminders': rent_due_reminders(),
            'overdue_notifications': overdue_notifications(),
        })

    # --- Global template variables
    @app.context_processor
    def inject_globals():
        return {'datetime': datetime}

    # --- App context for initial setup
    with app.app_context():
        app.mpesa_api = MpesaAPI()

        # Initialize database manager for read/write separation
        init_db_manager(app)

    return app
