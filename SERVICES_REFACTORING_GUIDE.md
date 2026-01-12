# Service Layer Refactoring Guide - MFUKO7

## Overview

The Service Layer has been implemented to extract business logic from route handlers, creating a cleaner separation of concerns and making the codebase more maintainable and testable.

**Key Benefits:**
- ✅ Thinner, more readable route handlers
- ✅ Easier unit testing (mock services instead of entire app)
- ✅ Reusable business logic across different endpoints
- ✅ Easier future migration to FastAPI or microservices
- ✅ Centralized error handling
- ✅ Consistent logging and validation

---

## Service Layer Architecture

```
app/
├── services/
│   ├── __init__.py                    # Exports all services
│   ├── payment_service.py             # Payment operations
│   ├── notification_service.py        # Email/SMS operations
│   ├── tenant_service.py              # Tenant operations
│   ├── property_service.py            # Property operations
│   └── report_service.py              # Report generation
│
├── routes.py                          # REFACTORED (thinner)
├── models.py                          # No changes
└── extensions.py                      # No changes
```

---

## Services Overview

### 1. PaymentService
Handles all payment-related operations.

**Key Methods:**
- `create_payment()` - Create new payment record
- `record_payment_offline()` - Record cash/check payments
- `initiate_mpesa_payment()` - Start M-Pesa STK push
- `get_payment_history()` - Get payment history for landlord
- `get_overdue_payments()` - Get overdue payment list
- `get_payment_metrics()` - Calculate dashboard metrics
- `check_duplicate_transaction()` - Validate transaction ID
- `get_recent_payments()` - Get recent payments for dashboard
- `update_payment_status()` - Update payment status

**Example Usage in Routes:**
```python
from app.services import PaymentService

@main.route('/payments/record', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def record_payment():
    form = RecordPaymentForm()
    
    if form.validate_on_submit():
        try:
            payment = PaymentService.create_payment(
                tenant_id=form.tenant_id.data,
                amount=form.amount.data,
                payment_method=form.payment_method.data,
                payment_date=form.payment_date.data,
                description=form.description.data,
                is_offline=form.is_offline.data
            )
            flash('Payment recorded successfully!', 'success')
            return redirect(url_for('main.payments_history'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
    
    return render_template('payments/record_payment.html', form=form)
```

---

### 2. NotificationService
Handles all notification operations (email and SMS).

**Key Methods:**
- `send_email()` - Send email
- `send_sms()` - Send SMS via Twilio
- `handle_payment_confirmation()` - Send payment receipt
- `send_rent_reminder()` - Send rent due reminder
- `send_overdue_notice()` - Send overdue payment notice
- `get_user_notification_preferences()` - Get user preferences
- `update_user_notification_preferences()` - Update preferences
- `should_send_notification()` - Check if should send
- `send_welcome_email()` - Welcome new user
- `send_password_reset_email()` - Password reset email

**Example Usage in Routes:**
```python
from app.services import NotificationService

@main.route('/tenant/pay', methods=['POST'])
@login_required
@roles_required('tenant')
def tenant_make_payment():
    # ... create payment ...
    
    # Send confirmation
    tenant = Tenant.query.get(payment.tenant_id)
    NotificationService.handle_payment_confirmation(tenant, payment)
    
    flash('Payment submitted successfully!', 'success')
    return redirect(url_for('main.tenant_dashboard'))
```

---

### 3. TenantService
Handles all tenant-related operations.

**Key Methods:**
- `create_tenant()` - Create new tenant
- `update_tenant()` - Update tenant info
- `get_tenant_by_id()` - Get tenant by ID
- `get_tenant_by_user_id()` - Get tenant profile for user
- `get_tenants_for_landlord()` - Get all landlord's tenants
- `get_tenants_for_property()` - Get tenants in property
- `assign_tenant_to_unit()` - Assign tenant to unit
- `unassign_tenant_from_unit()` - Remove tenant from unit
- `delete_tenant()` - Delete tenant
- `get_active_tenants()` - Get active tenants
- `get_tenant_rent_info()` - Get rent and payment info
- `create_or_get_tenant_profile()` - Get or create profile
- `get_available_properties_for_tenant()` - Get vacant units
- `extend_lease()` - Extend lease
- `terminate_lease()` - Terminate lease

**Example Usage in Routes:**
```python
from app.services import TenantService

@main.route('/tenants/add', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def tenant_add():
    form = TenantForm()
    
    if form.validate_on_submit():
        try:
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
            flash('Tenant added successfully!', 'success')
            return redirect(url_for('main.tenants_list'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
    
    return render_template('tenants/add_edit.html', form=form)
```

---

### 4. PropertyService
Handles all property-related operations.

**Key Methods:**
- `create_property()` - Create new property
- `update_property()` - Update property info
- `get_property_by_id()` - Get property by ID
- `get_landlord_properties()` - Get all landlord's properties
- `delete_property()` - Delete property
- `get_property_units()` - Get all property units
- `get_vacant_units()` - Get vacant units
- `get_occupied_units()` - Get occupied units
- `get_property_statistics()` - Get property stats
- `add_unit_to_property()` - Add new unit
- `remove_unit_from_property()` - Remove unit
- `update_unit_status()` - Update unit status
- `get_property_overview()` - Get all properties overview

**Example Usage in Routes:**
```python
from app.services import PropertyService

@main.route('/properties/add', methods=['GET', 'POST'])
@login_required
@roles_required('landlord')
def properties_add():
    form = PropertyForm()
    
    if form.validate_on_submit():
        try:
            property_obj = PropertyService.create_property(
                landlord_id=current_user.id,
                name=form.name.data,
                address=form.address.data,
                property_type=form.property_type.data,
                county_name=form.county_name.data,
                number_of_units=form.number_of_units.data,
                unit_numbers=form.unit_numbers.data.split(','),
                description=form.description.data
            )
            flash('Property added successfully!', 'success')
            return redirect(url_for('main.properties_list'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
    
    return render_template('properties/add_edit.html', form=form)
```

---

### 5. ReportService
Handles all report generation and export operations.

**Key Methods:**
- `get_financial_report()` - Generate financial report
- `get_occupancy_report()` - Generate occupancy report
- `get_tenant_report()` - Generate tenant report
- `get_payment_report()` - Generate payment report
- `export_financial_report_csv()` - Export as CSV
- `export_tenant_report_csv()` - Export tenant as CSV
- `get_monthly_revenue_trend()` - Get revenue trend
- `get_payment_method_distribution()` - Payment method breakdown

**Example Usage in Routes:**
```python
from app.services import ReportService

@main.route('/reports', methods=['GET', 'POST'])
@login_required
def reports():
    try:
        financial = ReportService.get_financial_report(current_user.id)
        occupancy = ReportService.get_occupancy_report(current_user.id)
        
        return render_template('reports/index.html',
                             financial=financial,
                             occupancy=occupancy)
    except Exception as e:
        flash(f'Error generating reports: {str(e)}', 'danger')
        return redirect(url_for('main.index'))
```

---

## Step-by-Step Refactoring Example

### BEFORE (Original Route - Business Logic Mixed)
```python
@main.route('/landlord/dashboard')
@login_required
@roles_required('landlord')
def landlord_dashboard():
    try:
        landlord_properties = Property.query.filter_by(landlord_id=current_user.id).all()
        property_ids = [p.id for p in landlord_properties]
        
        landlord_tenant_ids = [t.id for t in Tenant.query.filter(
            Tenant.property_id.in_(property_ids)
        ).all()]
        
        # Calculate metrics
        metrics = {}
        today = datetime.utcnow().date()
        current_month_start = today.replace(day=1)
        next_month_start = (datetime(
            today.year + (today.month == 12),
            (today.month % 12) + 1,
            1
        )).date()
        
        # Total collected
        total_collected = Payment.query.filter(
            Payment.tenant_id.in_(landlord_tenant_ids),
            Payment.payment_date >= current_month_start,
            Payment.payment_date < next_month_start,
            Payment.status == 'confirmed'
        ).with_entities(func.sum(Payment.amount)).scalar() or 0.00
        
        metrics['total_collected'] = round(total_collected, 2)
        
        # ... more complex logic ...
        
        return render_template('landlord_dashboard.html', metrics=metrics)
    
    except Exception as e:
        flash('Error loading dashboard', 'danger')
        return redirect(url_for('main.index'))
```

### AFTER (Refactored - Thin Route, Business Logic in Service)
```python
from app.services import PaymentService, PropertyService

@main.route('/landlord/dashboard')
@login_required
@roles_required('landlord')
def landlord_dashboard():
    try:
        # All business logic delegated to services
        metrics = PaymentService.get_payment_metrics(current_user.id)
        recent_payments = PaymentService.get_recent_payments(current_user.id)
        properties = PropertyService.get_property_overview(current_user.id)
        
        return render_template('landlord_dashboard.html',
                             metrics=metrics,
                             recent_payments=recent_payments,
                             properties=properties)
    
    except Exception as e:
        current_app.logger.error(f"Dashboard error: {str(e)}")
        flash('Error loading dashboard', 'danger')
        return redirect(url_for('main.index'))
```

---

## Migration Checklist

When refactoring a route, follow this checklist:

- [ ] Identify business logic in the route
- [ ] Move logic to appropriate service method
- [ ] Add proper error handling in service
- [ ] Add logging in service
- [ ] Update route to call service
- [ ] Keep authentication/authorization in route
- [ ] Keep template rendering in route
- [ ] Test the refactored route
- [ ] Update any other routes using same logic

---

## Testing Services

Services are now easier to unit test:

```python
# tests/test_payment_service.py
import unittest
from app import create_app
from app.services import PaymentService
from app.models import Payment, Tenant

class TestPaymentService(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
    
    def test_create_payment(self):
        # Create test data
        tenant = Tenant(...)  # Create test tenant
        
        # Call service directly
        payment = PaymentService.create_payment(
            tenant_id=tenant.id,
            amount=1500.00,
            payment_method='mpesa'
        )
        
        # Assert
        assert payment.id is not None
        assert payment.amount == 1500.00
```

---

## Common Patterns

### Pattern 1: Validation in Service
```python
def create_tenant(first_name, last_name, ...):
    # Validate input
    if not first_name or not first_name.strip():
        raise ValueError("First name is required")
    
    # Create object
    tenant = Tenant(...)
    db.session.add(tenant)
    db.session.commit()
    return tenant
```

### Pattern 2: Error Handling in Service
```python
def delete_tenant(tenant_id):
    try:
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        
        db.session.delete(tenant)
        db.session.commit()
        logger.info(f"Tenant deleted: {tenant_id}")
        return True
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting tenant: {str(e)}")
        raise
```

### Pattern 3: Complex Calculations in Service
```python
def get_payment_metrics(landlord_id):
    # All complex calculations happen here
    metrics = {}
    
    # Calculate each metric
    metrics['total_collected'] = ...
    metrics['collection_rate'] = ...
    metrics['recent_transactions'] = ...
    
    return metrics
```

---

## Best Practices

1. **Keep Services Stateless** - Services should not hold state, only process data
2. **Centralize Database Access** - All DB queries in services
3. **Consistent Error Handling** - Use exceptions, not return codes
4. **Comprehensive Logging** - Log all operations
5. **Single Responsibility** - Each service has one domain
6. **Return Plain Data** - Services return dicts/lists, not ORM objects when possible
7. **Validate Input** - Services validate all input data
8. **Transaction Management** - Services handle commits/rollbacks

---

## Next Steps

1. **Phase 1** (Routes to refactor):
   - `/landlord/dashboard` - Use PaymentService, PropertyService
   - `/payments/record` - Use PaymentService
   - `/payments/history` - Use PaymentService
   - `/tenants/add` - Use TenantService
   - `/properties/add` - Use PropertyService

2. **Phase 2** (Additional routes):
   - `/assign-property` - Use TenantService, PropertyService
   - `/tenant/pay` - Use PaymentService, NotificationService
   - `/reports` - Use ReportService

3. **Phase 3** (Authentication routes):
   - Create AuthService for auth/routes.py
   - Extract password reset logic
   - Extract OAuth logic

4. **Phase 4** (M-Pesa routes):
   - Create MpesaService for payment callbacks
   - Extract transaction verification
   - Extract token management

---

## File Locations

- Services: `/app/services/`
- Tests: `/tests/test_services/`
- Documentation: `/docs/services/`

All services are imported via `/app/services/__init__.py`

```python
from app.services import (
    PaymentService,
    NotificationService,
    TenantService,
    PropertyService,
    ReportService
)
```
