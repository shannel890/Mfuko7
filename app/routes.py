from flask import Blueprint, render_template, request, flash, current_app
from flask_security import auth_required, roles_accepted, current_user
from datetime import datetime, timedelta
from app.models import Property, Tenant, Payment
from flask_babel import lazy_gettext as _l
from app.extensions import db
from sqlalchemy import func

main = Blueprint('main', __name__)

@main.route('/')
@auth_required()
def index():
    return render_template('index.html')


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
