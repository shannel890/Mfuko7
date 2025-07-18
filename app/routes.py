from flask import Blueprint, render_template, request, flash, current_app, redirect, url_for, Response
from flask_login import login_required, current_user
from flask_babel import lazy_gettext as _l
from app.extensions import db, mail
from sqlalchemy import func
from app.forms import TenantForm, PropertyForm, RecordPaymentForm, ContactForm, TenantPaymentForm, ReportFilterForm, AssignPropertyForm
from app.models import Property, Tenant, Payment, Unit, Invoice
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
                return redirect(url_for('main.index'))
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
        return redirect(url_for('main.index'))

@main.route('/index')
def index():
    try:
        if current_user.is_authenticated:
            if current_user.has_role('landlord'):
                return redirect(url_for('main.landlord_dashboard'))
            elif current_user.has_role('tenant'):
                return redirect(url_for('main.tenant_dashboard'))
        return render_template('index.html', now=datetime.utcnow())
    except Exception as e:
        current_app.logger.error(f"Error loading index: {e}")
        flash(_l('An error occurred loading the page.'), 'danger')
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
        return redirect(url_for('main.index'))

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
        recent_payments = [{
            'tenant': 'Sarah Wanjiku',
            'property': 'Green Valley Apt 2B',
            'amount': 'KSh 25,000',
            'date': 'Dec 1, 2024',
            'status': 'paid'
        },
        {
            'tenant': 'John Kimani',
            'property': 'Sunset Heights 5A',
            'amount': 'KSh 30,000',
            'date': 'Nov 30, 2024',
            'status': 'paid'
        },
        {
            'tenant': 'Grace Achieng',
            'property': 'Palm Court 1C',
            'amount': 'KSh 20,000',
            'date': 'Nov 29, 2024',
            'status': 'overdue'
        }]
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
            landlord_tenants=landlord_tenants 
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

        # If no tenant profile exists, create one
        if not tenant:
            tenant = Tenant(
                user_id=current_user.id,
                first_name=current_user.first_name,
                last_name=current_user.last_name,
                email=current_user.email,
                status='active',
                grace_period_days=5
            )
            db.session.add(tenant)
            db.session.commit()
            flash(_l('Tenant profile created automatically. Please contact landlord to assign a unit.'), 'info')

        # Calculate rent due date for current month
        today = datetime.utcnow().date()
        current_month_start = today.replace(day=1)
        due_day = tenant.due_day_of_month or 1

        try:
            due_date = current_month_start.replace(day=due_day)
        except ValueError:
            # Handle months with fewer days (e.g., Feb 30)
            next_month = (current_month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
            due_date = next_month - timedelta(days=1)

        # Fetch all VACANT units
        vacant_units = Unit.query.filter_by(status='vacant').all()

        # Organize available properties with count of vacant units
        available_properties = {}
        for unit in vacant_units:
            property_obj = unit.property
            if not property_obj:
                continue  # In case of orphaned units

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

        # Convert dict to list for Jinja iteration
        available_properties_list = list(available_properties.values())

        return render_template(
            'tenant_dashboard.html',
            tenant=tenant,
            due_date=due_date,
            rent_amount=tenant.rent_amount,
            lease_start_date=tenant.lease_start_date,
            lease_end_date=tenant.lease_end_date,
            available_properties=available_properties_list
        )

    except Exception as e:
        current_app.logger.error(f"Tenant Dashboard Error: {str(e)}")
        flash(_l('An error occurred while loading the tenant dashboard.'), 'danger')
        return redirect(url_for('main.index'))



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
        return redirect(url_for('main.index'))


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
        if tenant_id:
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                flash(_l('Tenant not found.'), 'warning')
                return redirect(url_for('main.landlord_dashboard'))
        else:
            tenant = None

        properties = Property.query.filter_by(landlord_id=current_user.id).all()
        property_ids = [p.id for p in properties]
        units = Unit.query.filter(Unit.property_id.in_([p.id for p in properties]), Unit.status == 'vacant').all()

        form = AssignPropertyForm()
        form.property_id.choices = [(p.id, p.name) for p in properties]
        form.unit_id.choices = [(u.id, f"{u.unit_number} - {u.property.name}") for u in units]
        print("Vacant units:", [(u.id, u.unit_number, u.status) for u in units])
        form.tenant_id.choices = [(t.id, f"{t.first_name} {t.last_name}") for t in Tenant.query.all()]

        if form.validate_on_submit():
            tenant_id = form.tenant_id.data
            unit_id = form.unit_id.data
            tenant = Tenant.query.get(tenant_id)
            unit = Unit.query.get(unit_id)
            if tenant and unit:
                tenant.unit_id = unit.id
                tenant.property_id = unit.property_id
                unit.status = 'occupied'
                db.session.commit()
                flash(_l('Property assigned successfully!'), 'success')
                return redirect(url_for('main.landlord_dashboard'))
            else:
                flash(_l('Invalid tenant or unit selected.'), 'danger')
                print("Units:", [(u.id, u.status) for u in units])
                print("Form unit choices:", form.unit_id.choices)


        return render_template('assign_property.html', tenant=tenant, properties=properties, units=units, form=form)

    except Exception as e:
        logging.error("Assign property error:")
        logging.error(traceback.format_exc())
        flash(_l('An error occurred while loading the assignment page.'), 'danger')
        return redirect(url_for('main.landlord_dashboard'))

@main.route('/tenants')
@login_required
@roles_required('landlord')
def tenants_list():
    landlord_properties = Property.query.filter_by(landlord_id=current_user.id).all()
    property_ids = [p.id for p in landlord_properties]
    tenants = Tenant.query.filter(Tenant.property_id.in_(property_ids)).all()
    print("Landlord ID:", current_user.id)
    print("Property IDs:", property_ids)
    print("Filtered Tenants:", [(t.id, t.first_name) for t in Tenant.query.filter(Tenant.property_id.in_(property_ids)).all()])

    return render_template('tenants/list.html', tenants=tenants)

@main.route('/tenants/add', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def tenant_add():
    form = TenantForm()
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
            lease_end_date=form.lease_end_date.data,
            national_id=form.national_id.data,
            status=form.status.data
        )
        db.session.add(tenant)
        db.session.commit()
        flash(_l('Tenant added successfully!'), 'success')
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
        form.populate_obj(tenant)
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
        return redirect(url_for('main.index'))



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
        return redirect(url_for("main.index"))

    invoice = Invoice.query.filter_by(tenant_id=tenant.id, status='pending').first()
    amount_due = invoice.amount_due if invoice else tenant.rent_amount

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
            payment_date=form.payment_date.data,
            paybill_number=form.paybill_number.data,
            fees=form.fees.data,
            status='pending' if form.payment_method.data == 'mpesa' else 'completed',
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

            phone_number = current_user.phone_number
            if not phone_number:
                flash("Phone number not found in your profile. Please update it.", "danger")
                return redirect(url_for('auth.edit_profile'))

            current_app.logger.info(f"Phone number before formatting: {phone_number}")
            account_reference = f"Tenant-{tenant.id}"

            checkout_id = mpesa.initiate_stk_push(
                phone_number=phone_number,
                amount=form.amount.data,
                account_reference=account_reference,
                transaction_description='Monthly Rent'
            )

            if checkout_id:
                payment.transaction_id = checkout_id
                payment.status = 'pending'
                flash(_l('Payment initiated. Confirm on your phone.'), 'success')
            else:
                flash(_l('Payment initiation failed. Try again.'), 'danger')
                return redirect(url_for('main.tenant_make_payment'))

        db.session.add(payment)

        if invoice:
            invoice.amount_due -= payment.amount
            invoice.status = 'paid' if invoice.amount_due <= 0 else 'partially_paid'

        db.session.commit()
        flash("Your payment has been submitted.", "success")
        return redirect(url_for('main.tenant_dashboard'))

    return render_template(
        'payments/tenant_make_payment.html',
        form=form,
        amount_due=amount_due,
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
        return redirect(url_for('main.index'))

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

@main.route('/payment/delete/<int:payment_id>',methods=['GET','POST'])
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