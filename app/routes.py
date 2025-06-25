from flask import Blueprint, render_template, request, flash, current_app,redirect, url_for
from flask_security import auth_required, roles_accepted, current_user,login_required, roles_required
from datetime import datetime, timedelta
from app.models import Property, Tenant, Payment
from flask_babel import lazy_gettext as _l
from app.extensions import db
from sqlalchemy import func
from app.forms import TenantForm, PropertyForm, RecordPaymentForm
main = Blueprint('main', __name__)

@main.route('/')
@auth_required()
def index():
    return render_template('main/index.html')


@main.route('/admin')
@roles_accepted('admin')
def admin():
    return "<h1>Admin</h1>"

@main.route('/profile')
@auth_required()
def profile():
    return render_template('security/profile.html', user=current_user)

@main.route('/roles')
@roles_accepted('admin')
def roles():
    """
    Renders the roles page for admin users to manage roles.
    """
    return render_template('security/roles.html', roles=current_user.roles)

@main.route('/dashboard')
@auth_required()
def dashboard():
    """
    Renders the main dashboard with key metrics and recent payments for the logged-in landlord.
    """
    metrics = {
        'overdue_payments': 0,
        'total_collections': 0.00,
        'vacancy_rate': 0.00,
        'recent_transactions': 0
    }
    recent_payments = []

    try:
        # Fetch properties owned by the current landlord
        landlord_properties = Property.query.filter_by(landlord_id=current_user.id).all()
        landlord_property_ids = [p.id for p in landlord_properties]

        if landlord_property_ids:
            # Fetch active tenants
            landlord_tenants = Tenant.query.filter(
                Tenant.property_id.in_(landlord_property_ids),
                Tenant.status == 'active'
            ).all()
            landlord_tenant_ids = [t.id for t in landlord_tenants]

            today = datetime.utcnow().date()
            current_month_start = today.replace(day=1)

            if today.month == 12:
                next_month_start = datetime(today.year + 1, 1, 1).date()
            else:
                next_month_start = datetime(today.year, today.month + 1, 1).date()

            # 1. Overdue Payments
            overdue_count = 0
            for tenant in landlord_tenants:
                try:
                    due_day = tenant.due_day_of_month
                    if due_day is None:
                        current_app.logger.warning(
                            f"Tenant {tenant.id} has no due_day_of_month set. Skipping overdue calculation."
                        )
                        continue

                    try:
                        due_date_this_month = current_month_start.replace(day=due_day)
                    except ValueError:
                        last_day_of_month = (next_month_start - timedelta(days=1)).day
                        due_date_this_month = current_month_start.replace(day=last_day_of_month)

                    grace_period = tenant.grace_period_days or 0
                    effective_due_date = due_date_this_month + timedelta(days=grace_period)

                    if today > effective_due_date:
                        payment_this_month = Payment.query.filter(
                            Payment.tenant_id == tenant.id,
                            Payment.payment_date >= current_month_start,
                            Payment.payment_date < next_month_start,
                            Payment.status == 'confirmed'
                        ).first()

                        if not payment_this_month:
                            overdue_count += 1
                except Exception as overdue_e:
                    current_app.logger.error(
                        f"Error calculating overdue status for tenant {tenant.id}: {overdue_e}", exc_info=True
                    )
                    continue

            metrics['overdue_payments'] = overdue_count

            # 2. Total Collections
            total_collections_query = db.session.query(func.sum(Payment.amount)).filter(
                Payment.tenant_id.in_(landlord_tenant_ids),
                Payment.status == 'confirmed',
                Payment.payment_date >= current_month_start,
                Payment.payment_date < next_month_start
            ).scalar()
            metrics['total_collections'] = total_collections_query or 0.00

            # 3. Vacancy Rate
            total_units = db.session.query(func.sum(Property.number_of_units)).filter(
                Property.id.in_(landlord_property_ids)
            ).scalar() or 0

            occupied_units = len(landlord_tenants)

            if total_units > 0:
                metrics['vacancy_rate'] = round(((total_units - occupied_units) / total_units) * 100, 2)
            else:
                metrics['vacancy_rate'] = 0.00

            # 4. Recent Transactions
            seven_days_ago = datetime.utcnow().date() - timedelta(days=7)
            metrics['recent_transactions'] = Payment.query.filter(
                Payment.tenant_id.in_(landlord_tenant_ids),
                Payment.status == 'confirmed',
                Payment.payment_date >= seven_days_ago
            ).count()

            # Recent Payments Table (Last 5)
            recent_payments_query = Payment.query.filter(
                Payment.tenant_id.in_(landlord_tenant_ids),
                Payment.status == 'confirmed'
            ).order_by(Payment.payment_date.desc()).limit(5).all()

            for payment in recent_payments_query:
                tenant = payment.tenant
                property_name = tenant.property.name if tenant and tenant.property else _l('N/A')
                recent_payments.append({
                    'tenant_name': f"{tenant.first_name} {tenant.last_name}" if tenant else _l('Unknown Tenant'),
                    'property_name': property_name,
                    'amount': payment.amount,
                    'payment_date': payment.payment_date,
                    'status': payment.status
                })

    except Exception as e:
        current_app.logger.exception(
            f"Critical error fetching dashboard metrics for user {current_user.id}."
        )
        flash(_l('Error loading dashboard data. Please try again later.'), 'danger')

    return render_template('dashboard.html', metrics=metrics, recent_payments=recent_payments)

# --- Properties Routes ---
@main.route('/properties')
@login_required
@roles_required('landlord')
def properties_list():
    properties = Property.query.filter_by(landlord_id=current_user.id).all()
    return render_template('properties/list.html', properties=properties)

@main.route('/properties/add', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def property_add():
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
    landlord_properties = Property.query.filter_by(landlord_id=current_user.id).all()
    property_ids = [p.id for p in landlord_properties]
    # Filter tenants by properties belonging to the current landlord
    tenants = Tenant.query.filter(Tenant.property_id.in_(property_ids)).all()
    return render_template('tenants/list.html', tenants=tenants)

@main.route('/tenants/add', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def tenant_add():
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
    landlord_properties = Property.query.filter_by(landlord_id=current_user.id).all()
    property_ids = [p.id for p in landlord_properties]
    # Filter payments by tenants associated with the current landlord's properties
    tenant_ids = [t.id for t in Tenant.query.filter(Tenant.property_id.in_(property_ids)).all()]
    payments = Payment.query.filter(Payment.tenant_id.in_(tenant_ids)).order_by(Payment.payment_date.desc()).all()
    return render_template('payments/history.html', payments=payments)