"""
EXAMPLE: Refactored Routes Using Service Layer

This file demonstrates how to refactor existing routes to use the Service Layer.
Copy and adapt these patterns to your actual routes.py file.

Key Principles:
- Routes handle HTTP concerns (request/response, auth, rendering)
- Services handle business logic (database, calculations, validations)
- Thin routes, fat services = clean code
"""

from flask import Blueprint, render_template, request, flash, current_app, redirect, url_for
from flask_login import login_required, current_user
from flask_babel import lazy_gettext as _l

# Import services
from app.services import (
    PaymentService,
    NotificationService,
    TenantService,
    PropertyService,
    ReportService
)

from app.forms import (
    TenantForm, PropertyForm, RecordPaymentForm,
    TenantPaymentForm, ReportFilterForm
)

main = Blueprint('main', __name__)


# ============================================================================
# LANDLORD DASHBOARD - REFACTORED
# ============================================================================

@main.route('/landlord/dashboard')
@login_required
def landlord_dashboard():
    """
    Landlord dashboard showing overview metrics and recent activity.
    
    BEFORE: 150+ lines of complex logic
    AFTER: 20 lines using services
    """
    try:
        # All business logic delegated to services
        metrics = PaymentService.get_payment_metrics(current_user.id)
        recent_payments = PaymentService.get_recent_payments(current_user.id)
        properties = PropertyService.get_property_overview(current_user.id)
        
        return render_template(
            'landlord_dashboard.html',
            metrics=metrics,
            recent_payments=recent_payments,
            properties=properties
        )
    
    except Exception as e:
        current_app.logger.error(f"Dashboard error: {str(e)}")
        flash(_l('An error occurred while loading the dashboard.'), 'danger')
        return redirect(url_for('main.landing_page'))


# ============================================================================
# TENANT MANAGEMENT - REFACTORED
# ============================================================================

@main.route('/tenants')
@login_required
def tenants_list():
    """List all tenants for landlord."""
    try:
        tenants = TenantService.get_tenants_for_landlord(current_user.id)
        return render_template('tenants/list.html', tenants=tenants)
    
    except Exception as e:
        current_app.logger.error(f"Error fetching tenants: {str(e)}")
        flash(_l('Error loading tenants.'), 'danger')
        return redirect(url_for('main.index'))


@main.route('/tenants/add', methods=['GET', 'POST'])
@login_required
def tenant_add():
    """Add new tenant."""
    form = TenantForm()
    
    try:
        # Populate property choices
        properties = PropertyService.get_landlord_properties(current_user.id)
        form.property_id.choices = [(p.id, p.name) for p in properties]
        
        if form.validate_on_submit():
            # Delegate to service - no DB logic in route!
            tenant = TenantService.create_tenant(
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
                status=form.status.data
            )
            
            # Send welcome email if email provided
            if tenant.email:
                NotificationService.send_email(
                    subject="Welcome to MFUKO7",
                    recipients=[tenant.email],
                    body=f"Hi {tenant.first_name}, welcome to MFUKO7!"
                )
            
            flash(_l('Tenant added successfully!'), 'success')
            return redirect(url_for('main.tenants_list'))
    
    except ValueError as e:
        flash(f"Validation error: {str(e)}", 'danger')
    except Exception as e:
        current_app.logger.error(f"Error adding tenant: {str(e)}")
        flash(_l('An error occurred.'), 'danger')
    
    return render_template('tenants/add_edit.html', form=form, edit=False)


@main.route('/tenants/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def tenant_edit(id):
    """Edit tenant information."""
    try:
        tenant = TenantService.get_tenant_by_id(id)
        if not tenant:
            flash(_l('Tenant not found.'), 'warning')
            return redirect(url_for('main.tenants_list'))
        
        # Verify ownership
        properties = PropertyService.get_landlord_properties(current_user.id)
        property_ids = [p.id for p in properties]
        
        if tenant.property_id not in property_ids:
            flash(_l('You do not have permission to edit this tenant.'), 'danger')
            return redirect(url_for('main.tenants_list'))
        
        form = TenantForm(obj=tenant)
        form.property_id.choices = [(p.id, p.name) for p in properties]
        
        if form.validate_on_submit():
            # Update via service
            updated_tenant = TenantService.update_tenant(
                id,
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                email=form.email.data,
                phone_number=form.phone_number.data,
                rent_amount=form.rent_amount.data,
                due_day_of_month=form.due_day_of_month.data,
                grace_period_days=form.grace_period_days.data,
                status=form.status.data
            )
            
            flash(_l('Tenant updated successfully!'), 'success')
            return redirect(url_for('main.tenants_list'))
    
    except Exception as e:
        current_app.logger.error(f"Error editing tenant: {str(e)}")
        flash(_l('An error occurred.'), 'danger')
    
    return render_template('tenants/add_edit.html', form=form, edit=True)


@main.route('/tenant/delete/<int:tenant_id>', methods=['POST'])
@login_required
def delete_tenant(tenant_id):
    """Delete a tenant."""
    try:
        tenant = TenantService.get_tenant_by_id(tenant_id)
        if not tenant:
            flash(_l('Tenant not found.'), 'warning')
            return redirect(url_for('main.tenants_list'))
        
        # Verify ownership
        if tenant.property.landlord_id != current_user.id:
            flash(_l('Permission denied.'), 'danger')
            return redirect(url_for('main.tenants_list'))
        
        # Delete via service
        TenantService.delete_tenant(tenant_id)
        flash(_l('Tenant deleted successfully!'), 'success')
    
    except Exception as e:
        current_app.logger.error(f"Error deleting tenant: {str(e)}")
        flash(_l('Error deleting tenant.'), 'danger')
    
    return redirect(url_for('main.tenants_list'))


# ============================================================================
# PROPERTY MANAGEMENT - REFACTORED
# ============================================================================

@main.route('/properties')
@login_required
def properties_list():
    """List all properties for landlord."""
    try:
        properties = PropertyService.get_landlord_properties(current_user.id)
        return render_template('properties/list.html', properties=properties)
    
    except Exception as e:
        current_app.logger.error(f"Error fetching properties: {str(e)}")
        flash(_l('Error loading properties.'), 'danger')
        return redirect(url_for('main.index'))


@main.route('/properties/add', methods=['GET', 'POST'])
@login_required
def properties_add():
    """Add new property."""
    form = PropertyForm()
    
    try:
        if form.validate_on_submit():
            # Parse unit numbers
            unit_numbers = [u.strip() for u in form.unit_numbers.data.split(',')]
            
            # Delegate to service
            property_obj = PropertyService.create_property(
                landlord_id=current_user.id,
                name=form.name.data,
                address=form.address.data,
                property_type=form.property_type.data,
                county_name=form.county_name.data,
                number_of_units=form.number_of_units.data,
                unit_numbers=unit_numbers,
                description=form.description.data
            )
            
            flash(_l('Property added successfully!'), 'success')
            return redirect(url_for('main.properties_list'))
    
    except ValueError as e:
        flash(f"Validation error: {str(e)}", 'danger')
    except Exception as e:
        current_app.logger.error(f"Error adding property: {str(e)}")
        flash(_l('An error occurred.'), 'danger')
    
    return render_template('properties/add_edit.html', form=form, edit=False)


@main.route('/properties/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def properties_edit(id):
    """Edit property."""
    try:
        property_obj = PropertyService.get_property_by_id(id)
        if not property_obj:
            flash(_l('Property not found.'), 'warning')
            return redirect(url_for('main.properties_list'))
        
        # Verify ownership
        if property_obj.landlord_id != current_user.id:
            flash(_l('Permission denied.'), 'danger')
            return redirect(url_for('main.properties_list'))
        
        form = PropertyForm(obj=property_obj)
        
        if form.validate_on_submit():
            # Update via service
            PropertyService.update_property(
                id,
                name=form.name.data,
                address=form.address.data,
                property_type=form.property_type.data,
                description=form.description.data
            )
            
            flash(_l('Property updated successfully!'), 'success')
            return redirect(url_for('main.properties_list'))
    
    except Exception as e:
        current_app.logger.error(f"Error editing property: {str(e)}")
        flash(_l('An error occurred.'), 'danger')
    
    return render_template('properties/add_edit.html', form=form, edit=True)


@main.route('/property/delete/<int:property_id>', methods=['POST'])
@login_required
def delete_property(property_id):
    """Delete a property."""
    try:
        property_obj = PropertyService.get_property_by_id(property_id)
        if not property_obj:
            flash(_l('Property not found.'), 'warning')
            return redirect(url_for('main.properties_list'))
        
        if property_obj.landlord_id != current_user.id:
            flash(_l('Permission denied.'), 'danger')
            return redirect(url_for('main.properties_list'))
        
        PropertyService.delete_property(property_id)
        flash(_l('Property deleted successfully!'), 'success')
    
    except Exception as e:
        current_app.logger.error(f"Error deleting property: {str(e)}")
        flash(_l('Error deleting property.'), 'danger')
    
    return redirect(url_for('main.properties_list'))


# ============================================================================
# PAYMENT MANAGEMENT - REFACTORED
# ============================================================================

@main.route('/payments/record', methods=['GET', 'POST'])
@login_required
def record_payment():
    """Record a payment from tenant."""
    form = RecordPaymentForm()
    
    try:
        # Get landlord's tenants
        tenants = TenantService.get_tenants_for_landlord(current_user.id)
        form.tenant_id.choices = [
            (t.id, f"{t.first_name} {t.last_name} ({t.property.name})")
            for t in tenants
        ]
        
        if form.validate_on_submit():
            # Validate no duplicate transaction
            if form.transaction_id.data and not form.is_offline.data:
                existing = PaymentService.check_duplicate_transaction(
                    form.transaction_id.data
                )
                if existing:
                    flash("Transaction ID already used.", 'danger')
                    return redirect(request.url)
            
            # Create payment via service
            payment = PaymentService.create_payment(
                tenant_id=form.tenant_id.data,
                amount=form.amount.data,
                payment_method=form.payment_method.data,
                payment_date=form.payment_date.data,
                status='confirmed',
                transaction_id=form.transaction_id.data,
                description=form.description.data,
                is_offline=form.is_offline.data,
                offline_reference=form.offline_reference.data
            )
            
            # Send confirmation notification
            tenant = TenantService.get_tenant_by_id(payment.tenant_id)
            NotificationService.handle_payment_confirmation(tenant, payment)
            
            flash(_l('Payment recorded successfully!'), 'success')
            return redirect(url_for('main.payments_history'))
    
    except ValueError as e:
        flash(f"Error: {str(e)}", 'danger')
    except Exception as e:
        current_app.logger.error(f"Error recording payment: {str(e)}")
        flash(_l('An error occurred.'), 'danger')
    
    return render_template('payments/record_payment.html', form=form, tenants=tenants)


@main.route('/payments/history')
@login_required
def payments_history():
    """View payment history."""
    try:
        payments = PaymentService.get_payment_history(current_user.id)
        return render_template('payments/history.html', payments=payments)
    
    except Exception as e:
        current_app.logger.error(f"Error loading payment history: {str(e)}")
        flash(_l('Failed to load payment history.'), 'danger')
        return redirect(url_for('main.index'))


@main.route('/overdue/history')
@login_required
def overdue_payment():
    """View overdue payments."""
    try:
        overdue_tenants = PaymentService.get_overdue_payments(current_user.id)
        return render_template('payments/overdue_payment.html',
                             overdue_tenants=overdue_tenants)
    
    except Exception as e:
        current_app.logger.error(f"Error loading overdue payments: {str(e)}")
        flash(_l('Error loading overdue payments.'), 'danger')
        return redirect(url_for('main.index'))


@main.route('/tenant/pay', methods=['GET', 'POST'])
@login_required
def tenant_make_payment():
    """Tenant making a payment (M-Pesa or offline)."""
    form = TenantPaymentForm()
    
    try:
        # Get tenant profile
        tenant = TenantService.get_tenant_by_user_id(current_user.id)
        if not tenant:
            flash("Tenant profile not found.", "danger")
            return redirect(url_for("main.index"))
        
        # Get rent info
        rent_info = TenantService.get_tenant_rent_info(tenant.id)
        
        if form.validate_on_submit():
            # Check for duplicate transaction
            if form.transaction_id.data and not form.is_offline.data:
                if PaymentService.check_duplicate_transaction(form.transaction_id.data):
                    flash("Transaction ID already used.", 'danger')
                    return redirect(request.url)
            
            # Handle M-Pesa payment
            if form.payment_method.data == 'mpesa' and not form.is_offline.data:
                result = PaymentService.initiate_mpesa_payment(
                    tenant_id=tenant.id,
                    amount=form.amount.data,
                    phone_number=current_user.phone_number,
                    account_reference=f"Tenant-{tenant.id}"
                )
                
                if not result['success']:
                    flash(result['message'], 'danger')
                    return redirect(url_for('main.tenant_make_payment'))
                
                # Create payment record
                payment = PaymentService.create_payment(
                    tenant_id=tenant.id,
                    amount=form.amount.data,
                    payment_method='mpesa',
                    transaction_id=result['checkout_id'],
                    status='pending'
                )
            
            else:
                # Offline payment
                payment = PaymentService.record_payment_offline(
                    tenant_id=tenant.id,
                    amount=form.amount.data,
                    payment_date=form.payment_date.data,
                    payment_method=form.payment_method.data,
                    description=form.description.data,
                    offline_reference=form.offline_reference.data
                )
            
            # Send confirmation
            NotificationService.handle_payment_confirmation(tenant, payment)
            
            flash("Your payment has been submitted.", "success")
            return redirect(url_for('main.tenant_dashboard'))
    
    except Exception as e:
        current_app.logger.error(f"Error making payment: {str(e)}")
        flash("An error occurred.", 'danger')
    
    return render_template(
        'payments/tenant_make_payment.html',
        form=form,
        amount_due=rent_info['amount_due'],
        tenant=tenant
    )


@main.route('/payment/delete/<int:payment_id>', methods=['POST'])
@login_required
def delete_payment(payment_id):
    """Delete a payment record."""
    try:
        payment = PaymentService.get_payment_by_id(payment_id)
        # Note: You'll need to add get_payment_by_id to PaymentService
        
        if not payment:
            flash("Payment not found.", 'warning')
            return redirect(url_for('main.payments_history'))
        
        # Verify ownership (check via tenant -> property -> landlord)
        tenant = TenantService.get_tenant_by_id(payment.tenant_id)
        if tenant.property.landlord_id != current_user.id:
            flash("Permission denied.", 'danger')
            return redirect(url_for('main.payments_history'))
        
        # Note: You'll need to add delete_payment to PaymentService
        # PaymentService.delete_payment(payment_id)
        
        flash("Payment deleted successfully!", 'success')
    
    except Exception as e:
        current_app.logger.error(f"Error deleting payment: {str(e)}")
        flash("Error deleting payment.", 'danger')
    
    return redirect(url_for('main.payments_history'))


# ============================================================================
# REPORTS - REFACTORED
# ============================================================================

@main.route('/reports', methods=['GET', 'POST'])
@login_required
def reports():
    """Generate and view reports."""
    try:
        form = ReportFilterForm()
        
        # Get report data from service
        financial = ReportService.get_financial_report(current_user.id)
        occupancy = ReportService.get_occupancy_report(current_user.id)
        payments = ReportService.get_payment_report(current_user.id)
        revenue_trend = ReportService.get_monthly_revenue_trend(current_user.id)
        
        return render_template(
            'reports/index.html',
            financial=financial,
            occupancy=occupancy,
            payments=payments,
            revenue_trend=revenue_trend,
            form=form
        )
    
    except Exception as e:
        current_app.logger.error(f"Error generating reports: {str(e)}")
        flash(_l('Error generating reports.'), 'danger')
        return redirect(url_for('main.index'))


@main.route('/reports/export')
@login_required
def reports_export():
    """Export reports as CSV."""
    try:
        report_type = request.args.get('type', 'financial')
        
        if report_type == 'financial':
            csv_content = ReportService.export_financial_report_csv(current_user.id)
            filename = 'financial_report.csv'
        elif report_type == 'tenant':
            csv_content = ReportService.export_tenant_report_csv(current_user.id)
            filename = 'tenant_report.csv'
        else:
            flash("Invalid report type.", 'danger')
            return redirect(url_for('main.reports'))
        
        # Return as file download
        response = Response(csv_content, mimetype='text/csv')
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
    
    except Exception as e:
        current_app.logger.error(f"Error exporting report: {str(e)}")
        flash(_l('Error exporting report.'), 'danger')
        return redirect(url_for('main.reports'))


# ============================================================================
# NOTES
# ============================================================================
"""
KEY IMPROVEMENTS IN REFACTORED ROUTES:

1. MUCH SHORTER: Routes are now 10-20 lines vs 50-150+ lines
2. READABLE: Business logic is in service, routes show intent
3. TESTABLE: Easy to mock services in unit tests
4. MAINTAINABLE: Changes to business logic in one place
5. REUSABLE: Services can be used by multiple routes/blueprints
6. CONSISTENT: Error handling follows same pattern everywhere

PATTERNS USED:

1. Exception Handling:
   - Try/except wrapping all logic
   - Logging all errors
   - User-friendly flash messages

2. Authorization:
   - Verify resource ownership before operations
   - Use @login_required decorator
   - Check user_id against resource

3. Service Calls:
   - One or few service calls per route
   - Pass only necessary data
   - Handle returned results

4. User Feedback:
   - Success messages with flash()
   - Error messages with flash()
   - Appropriate redirects

NEXT STEPS TO IMPLEMENT:

1. Update /app/routes.py with these refactored routes
2. Add missing methods to services (e.g., get_payment_by_id)
3. Update tests to test services independently
4. Create new services for auth and M-Pesa
5. Document any remaining business logic in routes
"""
