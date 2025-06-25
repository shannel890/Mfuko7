from flask import Blueprint, render_template
from flask_security import login_required,roles_accepted
from app.utils.constrants import UserRoles
from app.models import User, Role
auth = Blueprint('auth',__name__)

@auth.route('/users')
@login_required
@roles_accepted(UserRoles.LANDLORD)
def users():
    """
    Display a list of users.
    Only accessible to users with the 'landlord' role.
    """
    users = User.query.all()
    return render_template('auth/users.html', users=users)