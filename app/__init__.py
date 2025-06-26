from flask import Flask
from flask_security import SQLAlchemySessionUserDatastore
from flask_security.utils import hash_password
from .extensions import db, security, babel
from .models import User, Role
from .routes import main
from .forms import ExtendedRegisterForm
import uuid
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
    UserDatastore = SQLAlchemySessionUserDatastore(db.session, User, Role)
    security.init_app(app, UserDatastore, register_form=ExtendedRegisterForm)
    app.register_blueprint(main)
    
    with app.app_context():
        db.create_all()
    # Create landlord user
        # Inside create_app() after db.create_all()
       


        landlord_role = Role.query.filter_by(name='landlord').first()
        if not landlord_role:
            landlord_role = Role(name='landlord')
            db.session.add(landlord_role)
            db.session.commit()
        landlord_user = User.query.filter_by(email='shannel@gmail.com').first()
        if not landlord_user:
            landlord_user = User(
                email='shannel@gmail.com',
                password=hash_password('shannel254'),
                first_name='shannel',
                last_name='kirui',
                fs_uniquifier=str(uuid.uuid4()),
                active=True,  # ✅ add this line
                roles=[landlord_role]
            )

            landlord_user.roles.append(landlord_role)
            db.session.add(landlord_user)
        db.session.commit() # This commit is correct here
    return app