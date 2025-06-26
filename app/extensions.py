from flask_sqlalchemy import SQLAlchemy
from flask_security import Security, SQLAlchemyUserDatastore
from flask_babel import Babel


db = SQLAlchemy()
security = Security()
babel = Babel()
userdatastore = None