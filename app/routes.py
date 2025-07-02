from flask import Blueprint, render_template, request, flash, current_app, redirect, url_for, Response
from flask_login import login_required, current_user
from flask_babel import lazy_gettext as _l
from app.extensions import db, mail
from sqlalchemy import func
from app.forms import TenantForm, PropertyForm, RecordPaymentForm, ContactForm, TenantPaymentForm, ReportFilterForm
from app.models import Property, Tenant, Payment, Unit, Invoice
from functools import wraps
from datetime import datetime, timedelta
import logging
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Message
import traceback
import csv
import uuid
from io import StringIO

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
        return render_template('index.html')
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
        recent_payments = []
        landlord_properties = Property.query.filter_by(landlord_id=current_user.id).all()
        landlord_property_ids = [p.id for p in landlord_properties]

        if landlord_property_ids:
            landlord_tenants = Tenant.query.filter(Tenant.property_id.in_(landlord_property_ids), Tenant.status == 'active').all()
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
            total_units = db.session.query(func.sum(Unit.id)).filter(
                Unit.property_id.in_(landlord_property_ids),
                Unit.status != 'maintenance'
            ).count() or 0
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

        return render_template('landlord_dashboard.html', metrics=metrics, recent_payments=recent_payments)

    except Exception as e:
        logging.error("Dashboard error occurred:")
        logging.error(traceback.format_exc())  # Logs the full traceback
        flash(_l('An error occurred while loading the dashboard. Please try again.'), 'danger')
        return redirect(url_for('main.index'))


@main.route('/tenant/dashboard')
@login_required
@roles_required('tenant')
def tenant_dashboard():
    try:
        tenant = Tenant.query.filter_by(user_id=current_user.id).first()
        if not tenant:
            flash(_l('No tenant profile found. Contact your landlord.'), 'warning')
            return redirect(url_for('main.index'))

        today = datetime.utcnow().date()
        current_month_start = today.replace(day=1)
        due_day = tenant.due_day_of_month or 1
        try:
            due_date = current_month_start.replace(day=due_day)
        except ValueError:
            due_date = (current_month_start.replace(day=1) + timedelta(days=31)).replace(day=1) - timedelta(days=1)

        units = Unit.query.filter(Unit.status == 'vacant').all()
        available_properties = {}
        for unit in units:
            prop = unit.property
            if prop.id not in available_properties:
                available_properties[prop.id] = {
                    'name': prop.name,
                    'address': prop.address,
                    'property_type': prop.property_type,
                    'units_available': 0
                }
            available_properties[prop.id]['units_available'] += 1
        available_properties = list(available_properties.values())

        return render_template('tenant_dashboard.html', tenant=tenant, due_date=due_date, available_properties=available_properties)

    except Exception as e:
        logging.error(f"Dashboard error: {str(e)}")
        flash(_l('An error occurred while loading the dashboard. Please try again.'), 'danger')
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
    try:
        form = PropertyForm()
        if form.validate_on_submit():
            property = Property(
                name=form.name.data,
                address=form.address.data,
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
        return render_template('properties/add_edit.html', form=form, edit=False)
    except Exception as e:
        current_app.logger.error(f"Error adding property: {e}")
        flash(_l('Failed to add property.'), 'danger')
        return redirect(url_for('main.properties_list'))

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
    tenants = Tenant.query.all()
    form.tenant_id.choices = [(tenant.id, tenant.name) for tenant in tenants]
    landlord_properties = Property.query.filter_by(landlord_id=current_user.id).all()
    property_ids = [p.id for p in landlord_properties]
    form.tenant_id.choices = [(t.id, f"{t.first_name} {t.last_name} ({t.property.name})")
                             for t in Tenant.query.filter(Tenant.property_id.in_(property_ids)).all()]
    if form.validate_on_submit():
        invoice = Invoice.query.filter_by(tenant_id=form.tenant_id.data, status='pending').first()
        payment = Payment(
            amount=form.amount.data,
            tenant_id=form.tenant_id.data,
            payment_method=form.payment_method.data,
            transaction_id=str(uuid.uuid()),
            payment_date=form.payment_date.data or datetime.utcnow().date(),
            status='confirmed',
            description=form.description.data,
            is_offline=form.is_offline.data,
            offline_reference=form.offline_reference.data,
            invoice_id=invoice.id if invoice else None
        )
        db.session.add(payment)
        if invoice:
            invoice.amount_due -= payment.amount
            invoice.status = 'paid' if invoice.amount_due <= 0 else 'partially_paid'
        db.session.commit()
        flash(_l('Payment recorded successfully!'), 'success')
        return redirect(url_for('main.payments_history'))
    return render_template('payments/record_payment.html', form=form)

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
        payment = Payment(
            amount=form.amount.data,
            tenant_id=tenant.id,
            payment_method=form.payment_method.data,
            transaction_id=form.transaction_id.data,
            payment_date=form.payment_date.data or datetime.utcnow().date(),
            status='pending',  # Set to 'confirmed' if auto-confirmed
            description=form.description.data,
            is_offline=form.is_offline.data,
            offline_reference=form.offline_reference.data,
            invoice_id=invoice.id if invoice else None
        )

        db.session.add(payment)
        if invoice:
            invoice.amount_due -= payment.amount
            invoice.status = 'paid' if invoice.amount_due <= 0 else 'partially_paid'
        db.session.commit()
        flash("Your payment has been submitted and is pending confirmation.", "success")
        return redirect(url_for('main.tenant_dashboard'))

    return render_template('payments/tenant_make_payment.html', form=form, amount_due=amount_due)




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

