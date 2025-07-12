from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_babel import Babel
from flask_mail import Mail
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from flask_apscheduler import APScheduler
from authlib.integrations.flask_client import OAuth
from twilio.rest import Client

import settings
oauth = OAuth()
scheduler = APScheduler()
db = SQLAlchemy()
login_manager = LoginManager()
babel = Babel()
mail = Mail()
migrate = Migrate()
csrf = CSRFProtect()
twilio_client = Client()


