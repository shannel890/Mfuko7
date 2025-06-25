from flask import Flask
from flask_security import FSQLALiteUserDatastore
from .extensions import db, security, babel
from .models import User, Role
from .routes import main
from .forms import ExtendedRegisterForm

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_ENGINES'] = {"default": 'sqlite:///app.db'}
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'my_precious'
    app.config['SECURITY_PASSWORD_SALT'] = 'my_precious_two'
    app.config['SECURITY_REGISTERABLE'] = True
    app.config['SECURITY_SEND_REGISTER_EMAIL'] = False
    app.config['SECURITY_USE_REGISTER_V2'] = True
    app.config['SECURITY_RECOVERABLE'] = True
    app.config['SECURITY_CHANGEABLE'] =True
    app.config['SECURITY_CONFIRMABLE'] = False
    db.init_app(app)
    babel.init_app(app)
    user_datastore = FSQLALiteUserDatastore(db, User, Role)
    security.init_app(app, user_datastore, register_form=ExtendedRegisterForm)
    app.register_blueprint(main)
    return app