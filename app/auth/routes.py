from flask import Blueprint, render_template, current_app, url_for, flash, redirect, session,request
from flask_login import login_required,login_user, logout_user, current_user
from app.models import User, Role, Tenant,County
from app.extensions import db, oauth
from app.forms import RegistrationForm, LoginForm, ForgotPasswordRequestForm, ResetPasswordForm, ExtendedEditProfileForm
import uuid
import logging
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask_babel import lazy_gettext as _l
from app.extensions import mail
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import traceback
import uuid
from app.utils.constrants import UserRoles
from sqlalchemy.exc import SQLAlchemyError

def generate_uniquifier():
    return str(uuid.uuid4())



auth = Blueprint('auth',__name__,url_prefix='/auth')
def send_email(subject, sender, recipients, text_body, html_body=None):
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    if html_body:
        msg.html = html_body
    mail.send(msg)
def get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])

def roles_required(*required_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('main.login'))
            user_roles = {role.name for role in current_user.roles}
            if not set(required_roles).issubset(user_roles):
                flash(_l('You do not have the required permissions to access this page.'), 'danger')
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@auth.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()

    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("This email is already registered. Please log in or use a different email.", "danger")
            return redirect(url_for('auth.register'))

        # Role logic
        selected_role_name = form.role.data.lower() if form.role.data else UserRoles.TENANT
        selected_enum_role = getattr(UserRoles, selected_role_name.upper(), UserRoles.TENANT)

        selected_role_obj = Role.query.filter_by(name=selected_role_name).first()
        if not selected_role_obj:
            flash(f"Role '{selected_role_name}' not found in the Role table. Contact admin.", "danger")
            return redirect(url_for('auth.register'))

        hashed_password = generate_password_hash(form.password.data)

        try:
            new_user = User(
                first_name=form.first_name.data.strip(),
                last_name=form.last_name.data.strip(),
                email=email,
                password=hashed_password,
                fs_uniquifier=str(uuid.uuid4()),
                active=True,
                role=selected_role_name
            )
            new_user.roles.append(selected_role_obj)

            db.session.add(new_user)
            db.session.flush()  # Ensures new_user.id is available before commit

            # If user is a tenant, create a Tenant record
            if selected_role_name == 'tenant':
                tenant = Tenant(
                    user_id=new_user.id,
                    first_name=new_user.first_name,
                    last_name=new_user.last_name,
                    email=new_user.email,
                    status='active',
                    grace_period_days=5
                )
                db.session.add(tenant)

            db.session.commit()

            flash("Registration successful! Please log in.", "success")
            return redirect(url_for('auth.login'))

        except SQLAlchemyError as e:
            db.session.rollback()
            flash("An error occurred during registration. Please try again.", "danger")
            print(f"Registration error: {str(e)}")
            return redirect(url_for('auth.register'))

    return render_template('security/register.html', form=form)

@auth.route('/auth/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        # Check if user is an OAuth-only user
        if user and user.is_oauth_user:
            flash("Please log in using Google.", "warning")
            return redirect(url_for("auth.login"))

        # Check password
        if user and check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            flash(_l('Logged in successfully!'), 'success')

            # Redirect by role
            if any(role.name == 'landlord' for role in user.roles):
                return redirect(url_for('main.landlord_dashboard'))
            elif any(role.name == 'tenant' for role in user.roles):
                return redirect(url_for('main.tenant_dashboard'))
            else:
                return redirect(url_for('main.index'))

        flash(_l('Invalid email or password.'), 'danger')

    return render_template('security/login.html', form=form)


@auth.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            try:
                # Generate reset token
                serializer = get_serializer()
                token = serializer.dumps(user.email, salt='password-reset-salt')
                
                # Create reset link
                reset_url = url_for('auth.reset_password', token=token, _external=True)
                
                # Send email
                msg = Message(
                    subject=_l('Password Reset Request'),
                    sender="shannelkirui739@gmail.com",
                    recipients=[user.email],
                    body=f"Please click the following link to reset your password: {reset_url}\n\n"
                         f"If you did not request a password reset, please ignore this email."
                )
                mail.send(msg)
                flash(_l('Password reset instructions have been sent to your email.'), 'success')
            except Exception as e:
                logging.error(f"Error sending password reset email: {str(e)}")
                flash(_l('An error occurred while sending reset instructions. Please try again.'), 'danger')
        else:
            flash(_l('Email address not found.'), 'danger')
        return redirect(url_for('main.login'))
    return render_template('security/forgot_password.html', form=form)

@auth.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        serializer = get_serializer()
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)  # 1-hour expiration
    except (SignatureExpired, BadSignature):
        flash(_l('The password reset link is invalid or has expired.'), 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash(_l('Email address not found.'), 'danger')
        return redirect(url_for('auth.forgot_password'))

    form = ResetPasswordForm()  
    if form.validate_on_submit():
        user.password = generate_password_hash(form.password.data)
        db.session.commit()
        flash(_l('Your password has been reset successfully. Please log in.'), 'success')
        return redirect(url_for('main.login'))
    return render_template('security/reset_password.html', form=form, token=token)

@auth.route('/logout')
@login_required
def logout():
    try:
        logout_user()
        flash(_l('You have been logged out.'), 'success')
        return redirect(url_for('auth.login'))
    except Exception as e:
        current_app.logger.error(f"Logout error: {e}")
        flash(_l('An error occurred while logging out.'), 'danger')
        return redirect(url_for('main.index'))

@auth.route('/edit/profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    try:
        form = ExtendedEditProfileForm(obj=current_user)

        # Populate role choices
        if current_user.has_role('admin'):
            form.roles.choices = [(role.id, _l(role.name)) for role in Role.query.all()]
        else:
            form.roles.choices = [(role.id, _l(role.name)) for role in current_user.roles]
            if request.method == 'GET':
                form.roles.data = [role.id for role in current_user.roles]
        form.county.choices = [(c.id, c.name) for c in County.query.all()]

        if form.validate_on_submit():
            current_user.username = form.username.data
            current_user.first_name = form.first_name.data
            current_user.email = form.email.data
            current_user.phone_number = form.phone_number.data
            current_user.county = County.query.filter_by(name=form.county.data).first()
            current_user.language = form.language.data

            if form.roles.data:
                current_user.roles = Role.query.filter(Role.id.in_(form.roles.data)).all()

            db.session.add(current_user)
            db.session.commit()

            flash(_l('Profile updated successfully!'), 'success')
            return redirect(url_for('auth.profile'))

        return render_template('security/edit_profile.html', user=current_user, edit_profile_form=form)

    except Exception as e:
        current_app.logger.error(f"Profile edit error: {traceback.format_exc()}")
        flash(_l('An error occurred while updating your profile.'), 'danger')
        return redirect(url_for('auth.profile'))


@auth.route('/profile')
@login_required
def profile():
    try:
        return render_template('security/profile.html', user=current_user)
    except Exception as e:
        current_app.logger.error(f"Profile view error: {traceback.format_exc()}")
        flash(_l('Unable to load your profile.'), 'danger')
        return redirect(url_for('main.index'))

@auth.route('/roles')
@roles_required('landlord')
def roles():
    try:
        return render_template('security/roles.html', roles=current_user.roles)
    except Exception as e:
        current_app.logger.error(f"Roles page error: {traceback.format_exc()}")
        flash(_l('Unable to load roles.'), 'danger')
        return redirect(url_for('main.index'))
    


# initialize OAuth in your app factory
def init_oauth(app):
    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        access_token_url='https://oauth2.googleapis.com/token',
        access_token_params=None,
        authorize_url='https://accounts.google.com/o/oauth2/auth',
        authorize_params={
            "access_type": "offline",
            "prompt": "consent"
        },
        api_base_url='https://www.googleapis.com/oauth2/v2/',
        client_kwargs={'scope': 'openid email profile'},
    )


@auth.route('/google-login')
def google_login():
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth.route('/google/callback')
def google_callback():
    token = oauth.google.authorize_access_token()
    user_info = oauth.google.get('https://openidconnect.googleapis.com/v1/userinfo').json()

    
    email = user_info.get("email")
    first_name = user_info.get("given_name")
    last_name = user_info.get("family_name")

    if not email:
        flash("Google login failed: email not returned.", "danger")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email).first()

    if not user:
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_oauth_user=True,
            active=True,
            role='tenant',
            fs_uniquifier=generate_uniquifier()
        )
        db.session.add(user)
        db.session.commit()

    login_user(user)
    tenant_role = Role.query.filter_by(name='tenant').first()
    if tenant_role:
        user.roles.append(tenant_role)
        db.session.commit()
    # Store in session
    session['user_id'] = user.id
    flash("Logged in with Google", "success")
    return redirect(url_for('main.tenant_dashboard'))
