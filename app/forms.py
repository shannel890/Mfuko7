from flask_security import RegisterFormV2
from wtforms import StringField, validators

class ExtendedRegisterForm(RegisterFormV2):
    first_name = StringField('First Name', validators=[validators.DataRequired()])
    last_name = StringField('Last Name', validators=[validators.DataRequired()])