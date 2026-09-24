from flask import Blueprint, render_template, request, flash, current_app, redirect, url_for, Response
from flask_login import login_required, current_user
from flask_babel import lazy_gettext as _l
from app.extensions import db, mail, csrf
from sqlalchemy import func
from app.forms import TenantForm, PropertyForm, RecordPaymentForm, ContactForm, TenantPaymentForm, ReportFilterForm, AssignPropertyForm
from app.models import Property, Tenant, Payment, Unit, Invoice, User
from functools import wraps
from datetime import datetime, timedelta
import logging
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Message
import traceback
import csv
import uuid
from sqlalchemy import extract
from io import StringIO
from app.mpesa.mpesa_api import MpesaAPI 
from app.notification import handle_payment_confirmation
main = Blueprint('main', __name__)


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
                return redirect(url_for('main.landing_page'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@main.route('/')
def landing_page():
    try:
        if current_user.is_authenticated:
            if current_user.has_role('landlord'):
                return redirect(url_for('main.landlord_dashboard'))
            elif current_user.has_role('tenant'):
                return redirect(url_for('main.tenant_dashboard'))
        return render_template('landing_page.html')
    except Exception as e:
        current_app.logger.error(f"Landing page error: {e}")
        flash(_l('An error occurred.'), 'danger')
        return redirect(url_for('main.landing_page'))

@main.route('/features')
def features():
    try:
        return render_template('features.html')
    except Exception as e:
        current_app.logger.error(f"Error loading features: {e}")
        flash(_l('An error occurred loading the page.'), 'danger')
        return redirect(url_for('main.landing_page'))

@main.route('/testimonials')
def testimonials():
    try:
        return render_template('testimonials.html')
    except Exception as e:
        current_app.logger.error(f"Error loading testimonials: {e}")
        flash(_l('An error occurred loading the page.'), 'danger')
        return redirect(url_for('main.landing_page'))

@main.route('/pricing')
def pricing():
    try:
        return render_template('pricing.html')
    except Exception as e:
        current_app.logger.error(f"Error loading pricing: {e}")
        flash(_l('An error occurred loading the page.'), 'danger')
        return redirect(url_for('main.landing_page'))

@main.route('/admin')
@roles_required('admin')
def admin():
    try:
        return render_template('admin.html')
    except Exception as e:
        current_app.logger.error(f"Admin page error: {e}")
        flash(_l('Failed to load admin page.'), 'danger')
        return redirect(url_for('main.landing_page'))

@main.route('/contact', methods=['GET', 'POST'])
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        try:
            send_email(
                subject=f"Contact Form Inquiry: {form.subject.data}",
                sender=current_app.config['MAIL_DEFAULT_SENDER'],
                recipients=[current_app.config['MAIL_DEFAULT_SENDER']],
                text_body=f"From: {form.name.data} <{form.email.data}>\n\nMessage:\n{form.message.data}",
                html_body=render_template('email/contact_inquiry.html', form=form)
            )
            flash(_l('Your message has been sent successfully!'), 'success')
            return redirect(url_for('main.contact'))
        except Exception as e:
            flash(_l('There was an error sending your message.'), 'danger')
            current_app.logger.error(f"Error sending contact email: {e}")
    return render_template('contact.html', title=_l('Contact Us'), form=form)


@main.route('/landlord/dashboard')
@login_required
@roles_required('landlord')
def landlord_dashboard():
    try:
        metrics = {
            'overdue_payments': 0,
            'total_collections': 0.00,
            'vacancy_rate': 0.00,
            'recent_transactions': 0
        }
        recent_payments = []
        landlord_tenants = []  # Initialize for later use
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

            # Overdue Payments
            for tenant in landlord_tenants:
                due_day = tenant.due_day_of_month or 1
                try:
                    due_date_this_month = current_month_start.replace(day=due_day)
                except ValueError:
                    due_date_this_month = (next_month_start - timedelta(days=1))
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

            # Total Collections
            metrics['total_collections'] = db.session.query(func.sum(Payment.amount)).filter(
                Payment.tenant_id.in_(landlord_tenant_ids),
                Payment.status == 'confirmed',
                Payment.payment_date >= current_month_start,
                Payment.payment_date < next_month_start
            ).scalar() or 0.00

            # Vacancy Rate
            total_units = db.session.query(func.count(Unit.id)).filter(
                Unit.property_id.in_(landlord_property_ids),
                Unit.status != 'maintenance'
            ).scalar() or 0

            occupied_units = len(Tenant.query.filter(
                Tenant.property_id.in_(landlord_property_ids),
                Tenant.status == 'active',
                Tenant.unit_id != None
            ).join(Unit, Tenant.unit_id == Unit.id).all())

            if total_units > 0:
                metrics['vacancy_rate'] = round(((total_units - occupied_units) / total_units) * 100, 2)
            else:
                metrics['vacancy_rate'] = 0.00

            # Recent Transactions
            seven_days_ago = today - timedelta(days=7)
            metrics['recent_transactions'] = Payment.query.filter(
                Payment.tenant_id.in_(landlord_tenant_ids),
                Payment.status == 'confirmed',
                Payment.payment_date >= seven_days_ago
            ).count()

            # Recent Payments Table (Last 5)
            recent_payments_query = Payment.query.filter(
                Payment.tenant_id.in_(landlord_tenant_ids),
                Payment.status == 'confirmed'
            ).join(Tenant).order_by(Payment.payment_date.desc()).limit(5).all()

            for payment in recent_payments_query:
                if isinstance(payment.payment_date, str):
                    payment.payment_date = datetime.strptime(payment.payment_date, "%Y-%m-%d")  # or adjust format
                payment.formatted_date = payment.payment_date.strftime("%d/%m/%Y")
                tenant = payment.tenant
                if not tenant:
                    continue
                recent_payments.append({
                    'tenant_name': f"{tenant.first_name} {tenant.last_name}" if tenant else 'Unknown',
                    'property_name': tenant.property.name if tenant and tenant.property else 'N/A',
                    'amount': payment.amount,
                    'payment_date': payment.payment_date,
                    'status': payment.status
                })

        return render_template(
            'landlord_dashboard.html',
            metrics=metrics,
            recent_payments=recent_payments,
            landlord_tenants=landlord_tenants,
            property_count=len(landlord_properties)
        )

    except Exception as e:
        logging.error("Dashboard error occurred:")
        logging.error(traceback.format_exc())  # Logs the full traceback
        flash(_l('An error occurred while loading the dashboard. Please try again.'), 'danger')
        return redirect(url_for('main.landing_page'))


@main.route('/tenant/dashboard')
@login_required
@roles_required('tenant')
def tenant_dashboard():
    try:
        tenant = Tenant.query.filter_by(user_id=current_user.id).first()

        if not tenant:
            normalized_email = current_user.email.strip().lower()
            tenant = Tenant.query.filter(
                db.func.lower(db.func.trim(Tenant.email)) == normalized_email,
                Tenant.user_id.is_(None)
            ).first()
            if tenant:
                tenant.user_id = current_user.id
                db.session.commit()
            else:
                tenant = Tenant(
                    user_id=current_user.id,
                    first_name=current_user.first_name,
                    last_name=current_user.last_name,
                    email=normalized_email,
                    status='active',
                    grace_period_days=5
                )
                db.session.add(tenant)
                db.session.commit()
                flash(_l('Tenant profile created automatically.'), 'info')

        landlord = tenant.property.landlord if tenant.property else None
        derived_landlord_id = landlord.id if landlord else None
        if tenant.landlord_id != derived_landlord_id:
            tenant.landlord_id = derived_landlord_id
            db.session.commit()

        today = datetime.utcnow().date()
        current_month_start = today.replace(day=1)
        due_day = tenant.due_day_of_month or 1

        try:
            due_date = current_month_start.replace(day=due_day)
        except ValueError:
            next_month = (current_month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
            due_date = next_month - timedelta(days=1)

        vacant_units = Unit.query.filter_by(status='vacant').all()
        available_properties = {}
        for unit in vacant_units:
            property_obj = unit.property
            if not property_obj:
                continue

            prop_id = property_obj.id
            if prop_id not in available_properties:
                available_properties[prop_id] = {
                    'id': prop_id,
                    'name': property_obj.name,
                    'address': property_obj.address,
                    'property_type': property_obj.property_type,
                    'units_available': 0
                }
            available_properties[prop_id]['units_available'] += 1

        available_properties_list = list(available_properties.values())

        return render_template(
            'tenant_dashboard.html',
            tenant=tenant,
            due_date=due_date,
            rent_amount=tenant.rent_amount,
            lease_start_date=tenant.lease_start_date,
            lease_end_date=tenant.lease_end_date,
            available_properties=available_properties_list,
            landlord=landlord
        )

    except Exception:
        db.session.rollback()
        current_app.logger.exception('Tenant dashboard failed')
        flash(_l('An error occurred while loading the tenant dashboard.'), 'danger')
        return redirect(url_for('main.landing_page'))



@main.route('/properties')
@login_required
@roles_required('landlord')
def properties_list():
    try:
        properties = Property.query.filter_by(landlord_id=current_user.id).all()
        return render_template('properties/list.html', properties=properties)
    except Exception as e:
        current_app.logger.error(f"Error fetching properties: {e}")
        flash(_l('Failed to load properties.'), 'danger')
        return redirect(url_for('main.landing_page'))


@main.route('/properties/add', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def property_add():
    form = PropertyForm()
    if form.validate_on_submit():
        try:
            property = Property(
                name=form.name.data,
                address=form.address.data,
                payment_method=form.payment_method.data or 'mpesa',
                status='pending',
                property_type=form.property_type.data,
                number_of_units=form.number_of_units.data,
                landlord_id=current_user.id,
                county_name=form.county.data,
                amenities=form.amenities.data,
                utility_bill_types=form.utility_bill_types.data,
                unit_numbers=form.unit_numbers.data,
                deposit_amount=form.deposit_amount.data,
                deposit_policy=form.deposit_policy.data
            )
            db.session.add(property)
            db.session.flush()
            unit_numbers = list(dict.fromkeys(
                number.strip()
                for number in form.unit_numbers.data.replace('\n', ',').split(',')
                if number.strip()
            ))
            for unit_number in unit_numbers:
                db.session.add(Unit(
                    property_id=property.id,
                    unit_number=unit_number,
                    rent_amount=0,
                    deposit_amount=form.deposit_amount.data or 0,
                    status='vacant'
                ))
            db.session.commit()
            flash(_l('Property added successfully!'), 'success')
            return redirect(url_for('main.properties_list'))
        except Exception as e:
            current_app.logger.error(f"Error adding property: {e}")
            flash(_l('Failed to add property.'), 'danger')
            db.session.rollback() 
            return redirect(url_for('main.properties_list'))
    else:
        print(form.errors) 
    return render_template('properties/add_edit.html', form=form, edit=False)


@main.route('/properties/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def property_edit(id):
    property = Property.query.get_or_404(id)
    if property.landlord_id != current_user.id:
        flash(_l('You do not have permission to edit this property.'), 'danger')
        return redirect(url_for('main.properties_list'))
    form = PropertyForm(obj=property)
    if form.validate_on_submit():
        form.populate_obj(property)
        db.session.commit()
        flash(_l('Property updated successfully!'), 'success')
        return redirect(url_for('main.properties_list'))
    return render_template('properties/add_edit.html', form=form, edit=True)

@main.route('/assign-property', defaults={'tenant_id': None}, methods=['GET', 'POST'])
@main.route('/assign-property/<int:tenant_id>', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def assign_property(tenant_id):
    try:
        tenant = None
        if tenant_id:
            tenant = Tenant.query.get(tenant_id)
            if (not tenant or not (
                    tenant.landlord_id == current_user.id
                    or (tenant.property and tenant.property.landlord_id == current_user.id)
            )):
                flash(_l('Tenant not found.'), 'warning')
                return redirect(url_for('main.landlord_dashboard'))

        # Get landlord's properties
        properties = Property.query.filter_by(landlord_id=current_user.id).all()
        property_ids = [p.id for p in properties]

        # Get vacant units in those properties
        units = Unit.query.filter(Unit.property_id.in_(property_ids), Unit.status == 'vacant').all()

        # Initialize form
        form = AssignPropertyForm()

        # Populate form choices
        form.property_id.choices = [(p.id, p.name) for p in properties]
        form.unit_id.choices = [(u.id, f"{u.unit_number} - {u.property.name}") for u in units]
        landlord_tenant_query = Tenant.query.filter(
            db.or_(
                Tenant.landlord_id == current_user.id,
                Tenant.property_id.in_(property_ids)
            )
        )
        form.tenant_id.choices = [
            (t.id, f"{t.first_name} {t.last_name}")
            for t in landlord_tenant_query.order_by(Tenant.first_name, Tenant.last_name).all()
        ]

        if request.method == 'GET' and tenant:
            form.tenant_id.data = tenant.id  # Pre-fill tenant if passed via URL

        if form.validate_on_submit():
            selected_property = Property.query.get(form.property_id.data)
            selected_tenant = Tenant.query.get(form.tenant_id.data)
            selected_unit = Unit.query.get(form.unit_id.data)

            if (selected_property and selected_property.landlord_id == current_user.id
                and selected_tenant and (
                    selected_tenant.landlord_id == current_user.id
                    or (selected_tenant.property and selected_tenant.property.landlord_id == current_user.id)
                )
                and selected_unit and selected_unit.property_id == selected_property.id
                and selected_unit.status == 'vacant'):
                previous_unit = selected_tenant.unit
                if previous_unit and previous_unit.id != selected_unit.id:
                    previous_unit.status = 'vacant'
                selected_tenant.unit_id = selected_unit.id
                selected_tenant.property_id = selected_unit.property_id
                selected_tenant.landlord_id = current_user.id
                selected_tenant.rent_amount = selected_unit.rent_amount
                selected_unit.status = 'occupied'
                db.session.commit()
                flash(_l('Property assigned successfully!'), 'success')
                return redirect(url_for('main.landlord_dashboard'))
            else:
                flash(_l('Invalid tenant or unit selected.'), 'danger')

        return render_template(
            'assign_property.html',
            tenant=tenant,
            properties=properties,
            units=units,
            form=form
        )

    except Exception:
        db.session.rollback()
        current_app.logger.exception('Assign property failed')
        flash(_l('An error occurred while loading the assignment page.'), 'danger')
        return redirect(url_for('main.landlord_dashboard'))
    
@main.route('/tenants')
@login_required
@roles_required('landlord')
def tenants_list():
    landlord_properties = Property.query.filter_by(landlord_id=current_user.id).all()
    property_ids = [p.id for p in landlord_properties]
    tenants = Tenant.query.filter(Tenant.property_id.in_(property_ids)).all()
    return render_template('tenants/list.html', tenants=tenants)

@main.route('/tenants/add', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def tenant_add():
    form = TenantForm()
    if request.method == 'POST' and form.email.data:
        form.email.data = form.email.data.strip().lower()
    properties = Property.query.filter_by(landlord_id=current_user.id).order_by(Property.name).all()
    property_ids = [property.id for property in properties]
    # Older property records saved unit numbers as text without creating Unit rows.
    # Backfill those missing rows so existing landlords can allocate their units too.
    for property in properties:
        recorded_numbers = {
            number.strip()
            for number in (property.unit_numbers or '').replace('\n', ',').split(',')
            if number.strip()
        }
        existing_numbers = {unit.unit_number for unit in property.units}
        for unit_number in recorded_numbers - existing_numbers:
            db.session.add(Unit(
                property_id=property.id,
                unit_number=unit_number,
                rent_amount=0,
                deposit_amount=property.deposit_amount or 0,
                status='vacant'
            ))
    if properties:
        db.session.commit()
    units = Unit.query.filter(Unit.property_id.in_(property_ids), Unit.status == 'vacant').order_by(Unit.unit_number).all() if property_ids else []
    form.property_id.choices = [(property.id, property.name) for property in properties]
    form.unit_id.choices = [(0, _l('Select a unit...'))] + [
        (unit.id, f"{unit.property.name} — {unit.unit_number}", {'data-property': str(unit.property_id)})
        for unit in units
    ]

    if form.validate_on_submit():
        selected_unit = Unit.query.filter_by(id=form.unit_id.data, status='vacant').first()
        property_ids_by_owner = {property.id for property in properties}
        if (not selected_unit or selected_unit.property_id not in property_ids_by_owner
                or selected_unit.property_id != form.property_id.data):
            form.unit_id.errors.append(_l('Choose a vacant unit in the selected property.'))
        else:
            normalized_email = form.email.data.strip().lower() if form.email.data else None
            existing_user = User.query.filter(
                db.func.lower(db.func.trim(User.email)) == normalized_email
            ).first() if normalized_email else None
            if existing_user and existing_user.role != 'tenant' and not existing_user.has_role('tenant'):
                form.email.errors.append(_l('This email belongs to a non-tenant account.'))
            else:
                tenant = existing_user.tenant_profile if existing_user else None
                if normalized_email and tenant is None:
                    tenant = Tenant.query.filter(
                        db.func.lower(db.func.trim(Tenant.email)) == normalized_email,
                        Tenant.user_id.is_(None)
                    ).order_by(
                        Tenant.unit_id.isnot(None).desc(),
                        Tenant.property_id.isnot(None).desc(),
                        Tenant.id.asc()
                    ).first()
                if tenant and tenant.user_id and (not existing_user or tenant.user_id != existing_user.id):
                    form.email.errors.append(_l('This email is already linked to another tenant account.'))
                elif tenant and tenant.unit_id and tenant.unit_id != selected_unit.id:
                    form.email.errors.append(_l('This tenant is already assigned to a unit.'))
                elif tenant and tenant.property and tenant.property.landlord_id != current_user.id:
                    form.email.errors.append(_l('This tenant is already assigned to another landlord.'))
                else:
                    if not tenant:
                        tenant = Tenant(
                            first_name=form.first_name.data.strip(),
                            last_name=form.last_name.data.strip(),
                            email=normalized_email,
                            phone_number=form.phone_number.data.strip(),
                            property_id=selected_unit.property_id,
                            unit_id=selected_unit.id,
                            rent_amount=form.rent_amount.data,
                            due_day_of_month=form.due_day_of_month.data,
                            grace_period_days=form.grace_period_days.data,
                            lease_start_date=form.lease_start_date.data,
                            lease_end_date=form.lease_end_date.data,
                            national_id=form.national_id.data,
                            status=form.status.data,
                            landlord_id=current_user.id,
                            user_id=existing_user.id if existing_user else None
                        )
                        db.session.add(tenant)
                    else:
                        tenant.first_name = form.first_name.data.strip()
                        tenant.last_name = form.last_name.data.strip()
                        tenant.phone_number = form.phone_number.data.strip()
                        tenant.property_id = selected_unit.property_id
                        tenant.unit_id = selected_unit.id
                        tenant.rent_amount = form.rent_amount.data
                        tenant.due_day_of_month = form.due_day_of_month.data
                        tenant.grace_period_days = form.grace_period_days.data
                        tenant.lease_start_date = form.lease_start_date.data
                        tenant.lease_end_date = form.lease_end_date.data
                        tenant.national_id = form.national_id.data
                        tenant.status = form.status.data
                        tenant.landlord_id = current_user.id
                        if existing_user:
                            tenant.user_id = existing_user.id

                    try:
                        selected_unit.status = 'occupied'
                        selected_unit.rent_amount = form.rent_amount.data
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                        current_app.logger.exception('Tenant allocation failed')
                        flash(_l('The tenant could not be allocated. Please try again.'), 'danger')
                    else:
                        flash(_l('Tenant added and unit assigned successfully!'), 'success')
                        return redirect(url_for('main.tenants_list'))

    return render_template('tenants/add_edit.html', form=form, edit=False)

@main.route('/tenants/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def tenant_edit(id):
    tenant = Tenant.query.get_or_404(id)
    if tenant.property.landlord_id != current_user.id:
        flash(_l('You do not have permission to edit this tenant.'), 'danger')
        return redirect(url_for('main.tenants_list'))
    form = TenantForm(obj=tenant)
    form.property_id.choices = [(p.id, p.name) for p in Property.query.filter_by(landlord_id=current_user.id).all()]
    if form.validate_on_submit():
        assigned_unit_id = tenant.unit_id
        form.populate_obj(tenant)
        tenant.unit_id = assigned_unit_id
        db.session.commit()
        flash(_l('Tenant updated successfully!'), 'success')
        return redirect(url_for('main.tenants_list'))
    return render_template('tenants/add_edit.html', form=form, edit=True)
    

@main.route('/payments/record', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def record_payment():
    form = RecordPaymentForm()

    # Get the landlord's properties
    landlord_properties = Property.query.filter_by(landlord_id=current_user.id).all()
    property_ids = [p.id for p in landlord_properties]

    # Filter tenants belonging to the landlord
    tenants = Tenant.query.filter(Tenant.property_id.in_(property_ids)).all()

    # Populate the tenant choices in the dropdown
    form.tenant_id.choices = [
        (t.id, f"{t.first_name} {t.last_name} ({t.property.name})")
        for t in tenants
    ]

    if form.validate_on_submit():
        # Get the tenant's first pending invoice (if any)
        invoice = Invoice.query.filter_by(
            tenant_id=form.tenant_id.data,
            status='pending'
        ).first()

        # Create and save payment
        payment = Payment(
            amount=form.amount.data,
            tenant_id=form.tenant_id.data,
            payment_method=form.payment_method.data,
            transaction_id=str(uuid.uuid4()),
            payment_date=form.payment_date.data or datetime.utcnow().date(),
            status='confirmed',
            description=form.description.data,
            is_offline=form.is_offline.data,
            offline_reference=form.offline_reference.data,
            invoice_id=invoice.id if invoice else None
        )

        db.session.add(payment)

        # Update invoice if available
        if invoice:
            invoice.amount_due -= payment.amount
            invoice.status = 'paid' if invoice.amount_due <= 0 else 'partially_paid'

        db.session.commit()

        flash(_l('Payment recorded successfully!'), 'success')
        return redirect(url_for('main.payments_history'))

    return render_template('payments/record_payment.html', form=form, tenants=tenants)


@main.route('/payments/history')
@login_required
@roles_required('landlord')
def payments_history():
    try:
        landlord_properties = Property.query.filter_by(landlord_id=current_user.id).all()
        property_ids = [p.id for p in landlord_properties]

        tenants = Tenant.query.filter(Tenant.property_id.in_(property_ids)).all()
        tenant_ids = [t.id for t in tenants]

        payments = Payment.query.filter(Payment.tenant_id.in_(tenant_ids)).order_by(Payment.payment_date.desc()).all()

        for p in payments:
            tenant = Tenant.query.get(p.tenant_id)
            p.tenant_name = f"{tenant.first_name} {tenant.last_name}"

        return render_template('payments/history.html', payments=payments)
    except Exception as e:
        current_app.logger.error(f"Error loading payment history: {e}")
        flash(_l('Failed to load payment history.'), 'danger')
        return redirect(url_for('main.landing_page'))



@main.route('/overdue/history')
@login_required
@roles_required('landlord')
def overdue_payment():
    landlord_properties = Property.query.filter_by(landlord_id=current_user.id).all()
    property_ids = [p.id for p in landlord_properties]
    tenant_ids = [t.id for t in Tenant.query.filter(Tenant.property_id.in_(property_ids)).all()]
    today = datetime.utcnow().date()
    current_month_start = today.replace(day=1)
    next_month_start = (datetime(today.year + (today.month == 12), (today.month % 12) + 1, 1)).date()
    overdue_tenants = []
    for tenant in Tenant.query.filter(Tenant.id.in_(tenant_ids), Tenant.status == 'active').all():
        due_day = tenant.due_day_of_month or 1
        try:
            due_date = current_month_start.replace(day=due_day)
        except ValueError:
            due_date = (next_month_start - timedelta(days=1))
        effective_due_date = due_date + timedelta(days=tenant.grace_period_days or 0)
        if today > effective_due_date:
            payment = Payment.query.filter(
                Payment.tenant_id == tenant.id,
                Payment.payment_date >= current_month_start,
                Payment.payment_date < next_month_start,
                Payment.status == 'confirmed'
            ).first()
            if not payment:
                overdue_tenants.append({
                    'tenant_name': f"{tenant.first_name} {tenant.last_name}",
                    'property_name': tenant.property.name,
                    'due_date': due_date,
                    'amount_due': tenant.rent_amount
                })
    return render_template('payments/overdue_payment.html', overdue_tenants=overdue_tenants)

@main.route('/tenant/pay', methods=['GET', 'POST'])
@login_required
@roles_required('tenant')
def tenant_make_payment():
    form = TenantPaymentForm()
    tenant = Tenant.query.filter_by(user_id=current_user.id).first()

    if not tenant:
        flash("Tenant profile not found.", "danger")
        return redirect(url_for("main.landing_page"))

    invoice = Invoice.query.filter(
        Invoice.tenant_id == tenant.id,
        Invoice.status.in_(['pending', 'partially_paid'])
    ).order_by(Invoice.issue_date.asc()).first()
    amount_due = invoice.amount_due if invoice else (tenant.rent_amount or 0)
    recent_payments = Payment.query.filter_by(tenant_id=tenant.id).order_by(
        Payment.payment_date.desc()
    ).limit(5).all()
    today = datetime.utcnow().date()
    due_day = tenant.due_day_of_month or 1
    try:
        due_date = today.replace(day=due_day)
    except ValueError:
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        due_date = next_month - timedelta(days=1)

    if form.validate_on_submit() and form.amount.data > amount_due:
        flash(_l('Payment cannot exceed the current amount due.'), 'danger')
        return redirect(url_for('main.tenant_make_payment'))

    if form.validate_on_submit():
        if form.transaction_id.data and not form.is_offline.data:
            existing = Payment.query.filter_by(transaction_id=form.transaction_id.data).first()
            if existing:
                flash("Transaction ID already used. Please check and try again.", "danger")
                return redirect(request.url)
        payment = Payment(
            amount=form.amount.data,
            tenant_id=tenant.id,
            payment_method=form.payment_method.data,
            transaction_id=form.transaction_id.data if not form.is_offline.data else None,
            payment_date=datetime.combine(form.payment_date.data, datetime.min.time()),
            paybill_number=form.paybill_number.data,
            fees=form.fees.data,
            status='pending' if form.payment_method.data == 'mpesa' and not form.is_offline.data else 'completed',
            is_offline=form.is_offline.data,
            offline_reference=form.offline_reference.data,
            description=form.description.data
        )
        


        # If online M-Pesa payment
        if form.payment_method.data == 'mpesa' and not form.is_offline.data:
            mpesa = current_app.mpesa_api  # ✅ Get the configured M-Pesa API instance

            # Ensure token is valid or refresh
            if not mpesa.is_token_valid():
                if not mpesa.refresh_token():
                    flash(_l("Failed to authenticate with M-Pesa. Try again later."), "danger")
                    return redirect(url_for("main.tenant_make_payment"))

            phone_number = tenant.phone_number or current_user.phone_number
            if not phone_number:
                flash("Phone number not found in your profile. Please update it.", "danger")
                return redirect(url_for('auth.profile'))

            current_app.logger.info(f"Phone number before formatting: {phone_number}")
            account_reference = f"Tenant-{tenant.id}"

            callback_url = current_app.config.get('MPESA_CALLBACK_URL', '')
            if not callback_url.startswith('https://') or 'example.com' in callback_url:
                flash(_l('M-Pesa needs a public HTTPS callback URL. Configure MPESA_CALLBACK_URL as your site URL ending in /mpesa/callback.'), 'danger')
                return redirect(url_for('main.tenant_make_payment'))

            checkout_id = mpesa.initiate_stk_push(
                phone_number=phone_number,
                amount=form.amount.data,
                account_reference=account_reference,
                transaction_description='Monthly Rent'
            )

            if checkout_id:
                payment.transaction_id = checkout_id
                payment.notes = f"STK checkout: {checkout_id}"
                payment.status = 'pending'
                flash(_l('Payment initiated. Confirm on your phone.'), 'success')
            else:
                flash(_l('Payment initiation failed. Try again.'), 'danger')
                return redirect(url_for('main.tenant_make_payment'))

        db.session.add(payment)

        if invoice and payment.status != 'pending':
            invoice.amount_due -= payment.amount
            invoice.status = 'paid' if invoice.amount_due <= 0 else 'partially_paid'

        db.session.commit()
        flash("Your payment has been submitted.", "success")
        return redirect(url_for('main.tenant_dashboard'))

    return render_template(
        'payments/tenant_make_payment.html',
        form=form,
        amount_due=amount_due,
        due_date=due_date,
        recent_payments=recent_payments,
        tenant=tenant
    )
# Mock data function (replace with database queries)
def get_report_data(property_id, start_date, end_date):
    # Ensure numeric values with defaults
    total_income = 0.0
    total_expenses = 0.0
    transactions = [
        {'date': '2025-06-01', 'description': 'Rent Payment - Unit A', 'amount': 1500.00, 'type': 'Income'},
        {'date': '2025-06-05', 'description': 'Maintenance - Plumbing', 'amount': -300.00, 'type': 'Expense'},
        {'date': '2025-06-10', 'description': 'Rent Payment - Unit B', 'amount': 1200.00, 'type': 'Income'},
    ]
    total_income = sum(t['amount'] for t in transactions if t['type'] == 'Income')
    total_expenses = sum(abs(t['amount']) for t in transactions if t['type'] == 'Expense')
    return {
        'total_income': float(total_income),  # Ensure float
        'total_expenses': float(total_expenses),  # Ensure float
        'net_profit': float(total_income - total_expenses),
        'transactions': transactions
    }

@main.route('/reports', methods=['GET', 'POST'])
@login_required
def reports():
    try:
        form = ReportFilterForm()
        form.property_id.choices = [('', 'All Properties')] + [(str(i), f'Property {i}') for i in range(1, 4)]
        report_data = {'total_income': 0.0, 'total_expenses': 0.0, 'net_profit': 0.0, 'transactions': []}
        if form.validate_on_submit():
            report_data = get_report_data(form.property_id.data, form.start_date.data, form.end_date.data)
        return render_template('report.html', form=form, report_data=report_data)
    except Exception as e:
        current_app.logger.error(f"Report error: {e}")
        flash(_l('Failed to generate report.'), 'danger')
        return redirect(url_for('main.landing_page'))

@main.route('/reports/export')
@login_required
def export_report():
    try:
        form = ReportFilterForm(request.args)
        report_data = get_report_data(form.property_id.data, form.start_date.data, form.end_date.data)
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Date', 'Description', 'Amount', 'Type'])
        for t in report_data['transactions']:
            writer.writerow([t['date'], t['description'], t['amount'], t['type']])
        output.seek(0)
        return Response(
            output,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=report.csv'}
        )
    except Exception as e:
        current_app.logger.error(f"CSV Export Error: {e}")
        flash(_l('Failed to export report.'), 'danger')
        return redirect(url_for('main.reports'))

@main.route('/tenant/delete/<int:tenant_id>', methods=['POST'])
@login_required
@roles_required('landlord')
def delete_tenant(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    db.session.delete(tenant)
    db.session.commit()
    flash('Tenant deleted successfully', 'success')
    return redirect(url_for('main.tenants_list'))

@main.route('/payment/delete/<int:payment_id>',methods=['POST'])
@login_required
@roles_required('landlord')
def delete_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    db.session.delete(payment)
    db.session.commit()
    flash('payment deleted successfully','success')
    return redirect(url_for('main.payments_history'))
@main.route('/something')
def use_mpesa():
    return current_app.mpesa_api.ensure_valid_token()

@main.route('/property/delete/<int:property_id>', methods=['POST'])
@login_required
@roles_required('landlord')
def delete_property(property_id):
    property = Property.query.get_or_404(property_id)
    db.session.delete(property)
    db.session.commit()
    flash('Property deleted successfully', 'success')
    return redirect(url_for('main.properties_list'))

@main.route('/mpesa/callback', methods=['POST'])
@csrf.exempt
def mpesa_callback():
    data = request.get_json(silent=True) or {}
    result = (data.get('Body') or {}).get('stkCallback') or {}
    checkout_id = result.get('CheckoutRequestID')
    result_code = result.get('ResultCode')
    if not checkout_id or result_code is None:
        current_app.logger.warning('Received an invalid M-Pesa callback payload')
        return {'ResultCode': 1, 'ResultDesc': 'Invalid callback payload'}, 400

    payment = Payment.query.filter(
        db.or_(
            Payment.transaction_id == checkout_id,
            Payment.notes.like(f'%STK checkout: {checkout_id}%')
        )
    ).first()
    if not payment:
        current_app.logger.warning('M-Pesa callback did not match a pending checkout: %s', checkout_id)
        return {'ResultCode': 0, 'ResultDesc': 'Accepted'}

    try:
        if int(result_code) == 0:
            already_confirmed = payment.status == 'confirmed'
            items = ((result.get('CallbackMetadata') or {}).get('Item') or [])
            metadata = {item.get('Name'): item.get('Value') for item in items}
            receipt = metadata.get('MpesaReceiptNumber')
            amount = metadata.get('Amount')
            if receipt:
                payment.transaction_id = str(receipt)
            if amount is not None:
                payment.amount = amount
            payment.status = 'confirmed'
            payment.payment_date = datetime.utcnow()
            invoice = payment.invoice
            if invoice and not already_confirmed:
                invoice.amount_due = max(0, invoice.amount_due - payment.amount)
                invoice.status = 'paid' if invoice.amount_due <= 0 else 'partially_paid'
        else:
            payment.status = 'failed'
            payment.notes = (payment.notes or '') + f"\nM-Pesa failed: {result.get('ResultDesc', 'Payment was not completed')}"
        db.session.commit()
        return {'ResultCode': 0, 'ResultDesc': 'Accepted'}
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Unable to process M-Pesa callback for checkout %s', checkout_id)
        return {'ResultCode': 1, 'ResultDesc': 'Callback processing failed'}, 500
