from flask import Blueprint, render_template, request, url_for, flash, redirect
from flask_security import login_required,roles_accepted, roles_required
from app.utils.constrants import UserRoles
from app.models import User, Role, County
from extensions import db
auth = Blueprint('auth',__name__,url_prefix='/auth')

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

@auth.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])          
@login_required                                                               
@roles_required(UserRoles.LANDLORD)                                        
def edit_user(user_id):                                                        
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        user.username = request.form.get('username')
        user.first_name = request.form.get('first_name')
        user.email = request.form.get('email')
        user.phone_number = request.form.get('phone')
        user.county_id = request.form.get('county_id') or None
        user.language = request.form.get('language')

        # Update roles
        user.roles.clear()
        role_ids = request.form.getlist('roles')
        for role_id in role_ids:
            role = Role.query.get(role_id)
            if role:
                user.roles.append(role)

        try:
            db.session.commit()
            flash(f'User {user.email} updated successfully!', 'success')
            return redirect(url_for('auth.users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating user: {str(e)}', 'error')

    roles = Role.query.all()
    counties = County.query.filter_by(active=True).all()
    
    return render_template('auth/edit_user.html',
                           user=user,
                           roles=roles,
                           counties=counties)
