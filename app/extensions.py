from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_babel import Babel
from flask_mail import Mail
from flask_migrate import Migrate
db = SQLAlchemy()
login_manager = LoginManager()
babel = Babel()
mail = Mail()
migrate = Migrate()