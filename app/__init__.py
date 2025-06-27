from flask import Flask
from app.extensions import login_manager
from .extensions import db, babel
from .models import User, Role
from .routes import main
import os
import uuid
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
    
    db.init_app(app)
    babel.init_app(app)
    
    login_manager.init_app(app)
    login_manager.login_view = 'login'  # name of login route
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    app.register_blueprint(main)
    
    with app.app_context():
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
                password=('shannel254'),
                first_name='shannel',
                last_name='kirui',
                fs_uniquifier=str(uuid.uuid4()),
                active=True,  
                roles=[landlord_role]
            )

            landlord_user.roles.append(landlord_role)
            db.session.add(landlord_user)
        db.session.commit() # This commit is correct here
    return app