from flask import Blueprint, render_template, request, flash, current_app,redirect, url_for
from flask_login import login_required,current_user
from datetime import datetime, timedelta
from app.models import Property, Tenant, Payment, User, Role
from flask_login import login_user, logout_user
from flask_babel import lazy_gettext as _l
from app.extensions import db
from sqlalchemy import func
from app.forms import TenantForm, PropertyForm, RecordPaymentForm, ExtendedEditProfileForm, RegistrationForm, LoginForm
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

from functools import wraps
from flask import abort, redirect, url_for, flash
from flask_login import current_user

def roles_required(*required_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('main.login'))  # Or login manager's unauthorized

            # Get role names from current_user.roles
            user_roles = {role.name for role in current_user.roles}

            # Check if all required roles are present
            if not set(required_roles).issubset(user_roles):
                abort(403)  # Forbidden

            return f(*args, **kwargs)
        return decorated_function
    return decorator
main = Blueprint('main', __name__)

@main.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        new_user = User(
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            email=form.email.data,
            password=hashed_password,
            fs_uniquifier=str(uuid.uuid4()),
            active=True
        )

        # Assign a default role, e.g., 'tenant'
        default_role = Role.query.filter_by(name='tenant').first()
        if default_role:
            new_user.roles.append(default_role)

        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful! Please log in.')
        return redirect(url_for('main.login'))

    return render_template('security/register.html', form=form)

@main.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            flash('Logged in successfully!')
            return redirect(url_for('main.tenant_dashboard'))

        flash('Invalid email or password.')

    return render_template('security/login.html', form=form)

@main.route('/forgot_passord', methods=['GET','POST'])
def forgot_password():
    return render_template('security/forgot_password.html')

@main.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('main.login'))
@main.route('/')
def landing_page():
    """
    Renders the landing_page.html. If the user is authenticated,
    they are redirected to the dashboard. Otherwise, they remain
    on the landing page to decide whether to log in.
    """
    if current_user.is_authenticated:
        # If the user is already logged in, redirect them to the dashboard
        return redirect(url_for('main.tenant_dashboard'))
    # If not logged in, show the landing page
    return render_template('landing_page.html')

@main.route('/index')
def index():
    """Renders the index.html page."""
    return render_template('index.html')

@main.route('/admin')
@roles_required('admin')
def admin():
    """Admin page, accessible only by users with the 'admin' role."""
    return "<h1>Admin</h1>"

@main.route('/edit/profile', methods=['GET', 'POST'])
@roles_required('landlord')
def edit_profile():
    
    form = ExtendedEditProfileForm(obj=current_user) # Populate form with current user's data
    role_choices = [(1, 'Landlord'), (2, 'Tenant'), (3, 'Guest')]
    form.roles.choices = role_choices
    if form.validate_on_submit():
        form.populate_obj(current_user)
        db.session.add(current_user)
        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for('main.profile'))
    return render_template('security/edit_profile.html', user=current_user, edit_profile_form=form)

@main.route('/profile')
@login_required
def profile():
    """User profile page, requires authentication."""
    return render_template('security/profile.html', user=current_user)

@main.route('/roles')
@roles_required('landlord')
def roles():
    """
    Renders the roles page for admin users to manage roles.
    Requires 'admin' role.
    """
    return render_template('security/roles.html', roles=current_user.roles)

@main.route('/landlord/dashboard')
@login_required
@roles_required('landlord')
def landlord_dashboard():
    """
    Renders the dashboard based on the user's role (landlord or tenant).
    Requires authentication.
    """
    try:
        if current_user.has_role('landlord'):
            # ----- LANDLORD DASHBOARD -----
            metrics = {
                'overdue_payments': 0,
                'total_collections': 0.00,
                'vacancy_rate': 0.00,
                'recent_transactions': 0
            }
            recent_payments = []

            # Get landlord's properties and tenants
            landlord_properties = Property.query.filter_by(landlord_id=current_user.id).all()
            landlord_property_ids = [p.id for p in landlord_properties]

            if landlord_property_ids:
                landlord_tenants = Tenant.query.filter(
                    Tenant.property_id.in_(landlord_property_ids),
                    Tenant.status == 'active'
                ).all()
                landlord_tenant_ids = [t.id for t in landlord_tenants]

                today = datetime.utcnow().date()
                current_month_start = today.replace(day=1)
                next_month_start = (datetime(today.year + (today.month == 12), (today.month % 12) + 1, 1)).date()

                # 1. Overdue Payments
                for tenant in landlord_tenants:
                    due_day = tenant.due_day_of_month
                    if due_day is None:
                        continue
                    try:
                        due_date_this_month = current_month_start.replace(day=due_day)
                    except ValueError:
                        last_day_of_month = (next_month_start - timedelta(days=1)).day
                        due_date_this_month = current_month_start.replace(day=last_day_of_month)
                    effective_due_date = due_date_this_month + timedelta(days=tenant.grace_period_days or 0)

                    if today > effective_due_date:
                        payment_this_month = Payment.query.filter(
                            Payment.tenant_id == tenant.id,
                            Payment.payment_date >= current_month_start,
                            Payment.payment_date < next_month_start,
                            Payment.status == 'confirmed'
                        ).first()
                        if not payment_this_month:
                            metrics['overdue_payments'] += 1

                # 2. Total Collections
                metrics['total_collections'] = db.session.query(func.sum(Payment.amount)).filter(
                    Payment.tenant_id.in_(landlord_tenant_ids),
                    Payment.status == 'confirmed',
                    Payment.payment_date >= current_month_start,
                    Payment.payment_date < next_month_start
                ).scalar() or 0.00

                # 3. Vacancy Rate
                total_units = db.session.query(func.sum(Property.number_of_units)).filter(
                    Property.id.in_(landlord_property_ids)
                ).scalar() or 0
                metrics['vacancy_rate'] = round(((total_units - len(landlord_tenants)) / total_units) * 100, 2) if total_units else 0.00

                # 4. Recent Transactions
                seven_days_ago = today - timedelta(days=7)
                metrics['recent_transactions'] = Payment.query.filter(
                    Payment.tenant_id.in_(landlord_tenant_ids),
                    Payment.status == 'confirmed',
                    Payment.payment_date >= seven_days_ago
                ).count()

                # 5. Recent Payments Table (Last 5)
                recent_payments_query = Payment.query.filter(
                    Payment.tenant_id.in_(landlord_tenant_ids),
                    Payment.status == 'confirmed'
                ).order_by(Payment.payment_date.desc()).limit(5).all()

                for payment in recent_payments_query:
                    tenant = payment.tenant
                    recent_payments.append({
                        'tenant_name': f"{tenant.first_name} {tenant.last_name}" if tenant else 'Unknown',
                        'property_name': tenant.property.name if tenant and tenant.property else 'N/A',
                        'amount': payment.amount,
                        'payment_date': payment.payment_date,
                        'status': payment.status
                    })

            return render_template('landlord_dashboard.html', metrics=metrics, recent_payments=recent_payments)
        else:
            flash('Unauthorized role.', 'danger')
            return redirect(url_for('main.logout'))

    except Exception as e:
        current_app.logger.exception(f"Dashboard error: {e}")
        flash('An error occurred while loading the dashboard.', 'danger')
        return redirect(url_for('main.index'))
@main.route('/tenant/dashboard')
@login_required
@roles_required('tenant')
def tenant_dashboard():
    try:
        if current_user.has_role('tenant'):
            # ----- TENANT DASHBOARD -----
            tenant = Tenant.query.filter_by(user_id=current_user.id).first()
            if not tenant:
                flash('No tenant profile found.', 'warning')
                return redirect(url_for('main.index'))

            today = datetime.utcnow().date()
            due_day = tenant.due_day_of_month or 1
            try:
                due_date = today.replace(day=due_day)
            except ValueError:
                last_day = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                due_date = last_day

            # Get available properties
            all_properties = Property.query.all()
            occupied_property_ids = db.session.query(Tenant.property_id).distinct()
            available_properties = [p for p in all_properties if p.id not in [row[0] for row in occupied_property_ids]]

            return render_template('tenant_dashboard.html', tenant=tenant, due_date=due_date, available_properties=available_properties)

        else:
            flash('Unauthorized role.', 'danger')
            return redirect(url_for('main.logout'))

    except Exception as e:
        current_app.logger.exception(f"Dashboard error: {e}")
        flash('An error occurred while loading the dashboard.', 'danger')
        return redirect(url_for('main.index'))


# --- Properties Routes ---
@main.route('/properties')
@login_required
@roles_required('landlord')
def properties_list():
    """Lists properties owned by the current landlord."""
    properties = Property.query.filter_by(landlord_id=current_user.id).all()
    return render_template('properties/list.html', properties=properties)

@main.route('/properties/add', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def property_add():
    """Allows a landlord to add a new property."""
    form = PropertyForm()
    if form.validate_on_submit():
        property = Property(
            name=form.name.data,
            address=form.address.data,
            property_type=form.property_type.data,
            number_of_units=form.number_of_units.data,
            landlord_id=current_user.id
        )
        db.session.add(property)
        db.session.commit()
        flash(_l('Property added successfully.'), 'success')
        return redirect(url_for('main.properties_list'))
    return render_template('properties/add_edit.html', form=form, edit=False)

@main.route('/properties/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def property_edit(id):
    """Allows a landlord to edit an existing property."""
    property = Property.query.get_or_404(id)
    # Ensure the landlord owns this property
    if property.landlord_id != current_user.id:
        flash(_l('Access denied.'), 'danger')
        return redirect(url_for('main.properties_list'))
    form = PropertyForm(obj=property)
    if form.validate_on_submit():
        property.name = form.name.data
        property.address = form.address.data
        property.property_type = form.property_type.data
        property.number_of_units = form.number_of_units.data
        db.session.commit()
        flash(_l('Property updated successfully.'), 'success')
        return redirect(url_for('main.properties_list'))
    return render_template('properties/add_edit.html', form=form, edit=True)

# --- Tenants Routes ---
@main.route('/tenants')
@login_required
@roles_required('landlord')
def tenants_list():
    """Lists tenants associated with the current landlord's properties."""
    landlord_properties = Property.query.filter_by(landlord_id=current_user.id).all()
    property_ids = [p.id for p in landlord_properties]
    # Filter tenants by properties belonging to the current landlord
    tenants = Tenant.query.filter(Tenant.property_id.in_(property_ids)).all()
    return render_template('tenants/list.html', tenants=tenants)

@main.route('/tenants/add', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def tenant_add():
    """Allows a landlord to add a new tenant."""
    form = TenantForm()
    # Populate property choices with only properties belonging to the current landlord
    form.property_id.choices = [(p.id, p.name) for p in Property.query.filter_by(landlord_id=current_user.id).all()]
    if form.validate_on_submit():
        tenant = Tenant(
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            email=form.email.data,
            phone_number=form.phone_number.data,
            property_id=form.property_id.data,
            rent_amount=form.rent_amount.data,
            due_day_of_month=form.due_day_of_month.data,
            grace_period_days=form.grace_period_days.data,
            lease_start_date=form.lease_start_date.data,
            lease_end_date=form.lease_end_date.data
        )
        db.session.add(tenant)
        db.session.commit()
        flash(_l('Tenant added successfully.'), 'success')
        return redirect(url_for('main.tenants_list'))
    return render_template('tenants/add_edit.html', form=form, edit=False)

@main.route('/tenants/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def tenant_edit(id):
    """Allows a landlord to edit an existing tenant."""
    tenant = Tenant.query.get_or_404(id)
    # Ensure the tenant is associated with a property owned by the current landlord
    if tenant.property.landlord_id != current_user.id:
        flash(_l('Access denied.'), 'danger')
        return redirect(url_for('main.tenants_list'))
    form = TenantForm(obj=tenant)
    form.property_id.choices = [(p.id, p.name) for p in Property.query.filter_by(landlord_id=current_user.id).all()]
    if form.validate_on_submit():
        form.populate_obj(tenant) # Populate all fields from the form object
        db.session.commit()
        flash(_l('Tenant updated successfully.'), 'success')
        return redirect(url_for('main.tenants_list'))
    return render_template('tenants/add_edit.html', form=form, edit=True)

# --- Payments Routes ---
@main.route('/payments/record', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def record_payment():
    """Allows a landlord to record a new payment."""
    form = RecordPaymentForm()
    landlord_properties = Property.query.filter_by(landlord_id=current_user.id).all()
    property_ids = [p.id for p in landlord_properties]
    # Populate tenant choices only for tenants associated with the current landlord's properties
    form.tenant_id.choices = [(t.id, f"{t.first_name} {t.last_name}")
                              for t in Tenant.query.filter(Tenant.property_id.in_(property_ids)).all()]
    if form.validate_on_submit():
        payment = Payment(
            amount=form.amount.data,
            tenant_id=form.tenant_id.data,
            payment_method=form.payment_method.data,
            transaction_id=form.transaction_id.data,
            payment_date=form.payment_date.data or datetime.utcnow().date(), # Use .date() for consistency
            status='confirmed' # Manually recorded payments are confirmed by default
        )
        db.session.add(payment)
        db.session.commit()
        flash(_l('Payment recorded successfully.'), 'success')
        return redirect(url_for('main.payments_history'))
    return render_template('payments/record_payment.html', form=form)

@main.route('/payments/history')
@login_required
@roles_required('landlord')
def payments_history():
    """Displays a history of payments for the current landlord's properties."""
    landlord_properties = Property.query.filter_by(landlord_id=current_user.id).all()
    property_ids = [p.id for p in landlord_properties]
    # Filter payments by tenants associated with the current landlord's properties
    tenant_ids = [t.id for t in Tenant.query.filter(Tenant.property_id.in_(property_ids)).all()]
    payments = Payment.query.filter(Payment.tenant_id.in_(tenant_ids)).order_by(Payment.payment_date.desc()).all()
    return render_template('payments/history.html', payments=payments)


@main.route('/overdue/history')
@login_required
def overdue_payment():
    """Displays overdue payments for the current user."""
    # Your overdue payment logic here
    return render_template('/payments/overdue_payment.html')