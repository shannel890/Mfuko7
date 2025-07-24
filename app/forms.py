from wtforms import StringField, SubmitField, BooleanField, SelectField, TelField, DecimalField, DateField, TextAreaField, IntegerField, SelectMultipleField, PasswordField
from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError, NumberRange, EqualTo
from app.models import Property, Tenant, Role
from flask import current_app
from app.utils.constrants import UserRoles
class RegistrationForm(FlaskForm):
    first_name = StringField(_l('First Name'), validators=[DataRequired()])
    last_name = StringField(_l('Last Name'), validators=[DataRequired()])
    email = StringField(_l('Email'), validators=[DataRequired(), Email()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    confirm_password = PasswordField(_l('Confirm Password'), validators=[DataRequired(), EqualTo('password')])
    role = SelectField(_l('Role'), choices=[('tenant', _l('Tenant')), ('landlord', _l('Landlord'))], validators=[Optional()])
    submit = SubmitField(_l('Register'))

class LoginForm(FlaskForm):
    email = StringField(_l('Email'), validators=[DataRequired(), Email()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    remember = BooleanField(_l('Remember Me'))
    submit = SubmitField(_l('Login'))

class ForgotPasswordRequestForm(FlaskForm):
    email = StringField(_l('Email Address'), validators=[DataRequired(), Email()])
    submit = SubmitField(_l('Send Reset Instructions'))

class ResetPasswordForm(FlaskForm):
    password = PasswordField(_l('New Password'), validators=[
        DataRequired(),
        Length(min=8, message=_l('Password must be at least 8 characters long.')),
        EqualTo('confirm_password', message=_l('Passwords must match.'))
    ])
    confirm_password = PasswordField(_l('Confirm New Password'))
    submit = SubmitField(_l('Reset Password'))

class ContactForm(FlaskForm):
    """Form for users to send a message."""
    name = StringField(_l('Your Name'), validators=[DataRequired(), Length(max=100)])
    email = StringField(_l('Your Email'), validators=[DataRequired(), Email(), Length(max=120)])
    subject = StringField(_l('Subject'), validators=[DataRequired(), Length(max=200)])
    message = TextAreaField(_l('Message'), validators=[DataRequired(), Length(min=10, max=1000)])
    submit = SubmitField(_l('Send Message'))
class TenantForm(FlaskForm):
    property_id = SelectField(
        _l('Assigned Property'),
        validators=[DataRequired(_l('Property assignment is required.'))],
        coerce=int,
        choices=[],
        render_kw={"class": "form-select"}
    )
    first_name = StringField(
        _l('First Name'),
        validators=[
            DataRequired(_l('First name is required.')),
            Length(min=2, max=100, message=_l('First name must be between 2 and 100 characters.'))
        ],
        render_kw={"placeholder": _l("Tenant's first name")}
    )
    last_name = StringField(
        _l('Last Name'),
        validators=[
            DataRequired(_l('Last name is required.')),
            Length(min=2, max=100, message=_l('Last name must be between 2 and 100 characters.'))
        ],
        render_kw={"placeholder": _l("Tenant's last name")}
    )
    email = StringField(
        _l('Email (Optional)'),
        validators=[
            Optional(),
            Email(message=_l('Invalid email address.')),
            Length(max=120, message=_l('Email cannot exceed 120 characters.'))
        ],
        render_kw={"placeholder": _l("tenant@example.com")}
    )
    phone_number = TelField(
        _l('Phone Number'),
        validators=[
            DataRequired(_l('Phone number is required.')),
            Length(min=9, max=20, message=_l('Phone number must be between 9 and 20 characters.'))
        ],
        render_kw={"placeholder": _l("e.g., 0712345678")}
    )
    national_id = StringField(
        _l('National ID (Optional)'),
        validators=[
            Optional(),
            Length(min=6, max=30, message=_l('National ID must be between 6 and 30 characters.'))
        ],
        render_kw={"placeholder": _l("e.g., 12345678")}
    )
    status = SelectField(
        _l('Tenant Status'),
        validators=[DataRequired(_l('Tenant status is required.'))],
        choices=[
            ('active', _l('Active')),
            ('vacated', _l('Vacated')),
            ('evicted', _l('Evicted'))
        ],
        render_kw={"class": "form-select"}
    )
    rent_amount = DecimalField(
        _l('Monthly Rent Amount (KSh)'),
        validators=[
            DataRequired(_l('Rent amount is required.')),
            NumberRange(min=0.01, message=_l('Rent must be greater than 0.'))
        ],
        places=2,
        render_kw={"placeholder": _l("e.g., 15000.00")}
    )
    due_day_of_month = IntegerField(
        _l('Rent Due Day of Month'),
        validators=[
            DataRequired(_l('Due day is required.')),
            NumberRange(min=1, max=31, message=_l('Day must be between 1 and 31.'))
        ],
        render_kw={"placeholder": _l("e.g., 1 (for 1st of month)")}
    )
    grace_period_days = IntegerField(
        _l('Grace Period (days)'),
        validators=[
            DataRequired(_l('Grace period is required.')),
            NumberRange(min=0, message=_l('Grace period cannot be negative.'))
        ],
        render_kw={"placeholder": _l("e.g., 5")}
    )
    lease_start_date = DateField(
        _l('Lease Start Date'),
        validators=[DataRequired(_l('Lease start date is required.'))],
        format='%Y-%m-%d',
        render_kw={"placeholder": "YYYY-MM-DD"}
    )
    lease_end_date = DateField(
        _l('Lease End Date (Optional)'),
        validators=[Optional()],
        format='%Y-%m-%d',
        render_kw={"placeholder": "YYYY-MM-DD"}
    )
    submit = SubmitField(_l('Save Tenant'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from flask_security import current_user
            if current_user.is_authenticated and hasattr(current_user, 'has_role') and current_user.has_role('landlord'):
                properties = Property.query.filter_by(landlord_id=current_user.id).order_by(Property.name).all()
                self.property_id.choices = [(p.id, _l(p.name)) for p in properties]
            else:
                self.property_id.choices = []
        except Exception as e:
            current_app.logger.error(f"Error populating property choices for TenantForm: {e}")
            self.property_id.choices = []
        if not self.property_id.choices or self.property_id.choices[0][0] != 0:
            self.property_id.choices.insert(0, (0, _l('Select a Property...')))

    def validate_property_id(self, field):
        if field.data == 0:
            raise ValidationError(_l('Please select a property.'))

class PropertyForm(FlaskForm):
    name = StringField(
        _l('Property Name'),
        validators=[
            DataRequired(_l('Property name is required.')),
            Length(min=3, max=100, message=_l('Name must be between 3 and 100 characters.'))
        ],
        render_kw={"placeholder": _l("e.g., Sunny Apartments, Kilimani Block A")}
    )
    address = StringField(
        _l('Address'),
        validators=[
            DataRequired(_l('Address is required.')),
            Length(min=5, max=255, message=_l('Address must be between 5 and 255 characters.'))
        ],
        render_kw={"placeholder": _l("e.g., Plot 123, Off Ring Road, Nairobi")}
    )
    payment_method = SelectField('Payment Method', choices=[
        ('mpesa', 'M-Pesa'),
        ('bank', 'Bank Transfer'),
        ('cash', 'Cash')
    ], validators=[DataRequired()])
    
    property_type = SelectField(
        _l('Property Type'),
        validators=[DataRequired(_l('Property type is required.'))],
        choices=[
            ('', _l('Select Type...')),
            ('Apartment', _l('Apartment')),
            ('House', _l('House')),
            ('Commercial', _l('Commercial')),
            ('Other', _l('Other'))
        ],
        render_kw={"class": "form-select"}
    )
    number_of_units = IntegerField(
        _l('Number of Units'),
        validators=[
            DataRequired(_l('Number of units is required.')),
            NumberRange(min=1, message=_l('Must be at least 1 unit.'))
        ],
        render_kw={"placeholder": _l("e.g., 10")}
    )
    county = StringField(
        _l('County (Property Location)'),
        validators=[
            DataRequired(_l('County is required.')),
            Length(min=2, max=100, message=_l('County must be between 2 and 100 characters.'))
        ],
        render_kw={"placeholder": _l("e.g., Nairobi, Kilifi")}
    )
    amenities = TextAreaField(
        _l('Amenities (comma separated)'),
        validators=[Optional(), Length(max=500, message=_l('Amenities list too long.'))],
        render_kw={"rows": 3, "placeholder": _l("e.g., Swimming pool, Gym, Balcony")}
    )
    utility_bill_types = TextAreaField(
        _l('Utility Bill Types (comma separated)'),
        validators=[Optional(), Length(max=255, message=_l('Utility types list too long.'))],
        render_kw={"rows": 2, "placeholder": _l("e.g., Water, Electricity, Garbage")}
    )
    unit_numbers = TextAreaField(
    _l('Unit Numbers'),
    validators=[
        DataRequired(_l('At least one unit number is required.')),
        Length(max=500, message=_l('Unit numbers list too long.'))
    ],
    render_kw={"rows": 3, "placeholder": _l("e.g., A1, B2, Penthouse"), "class": "form-control"}
)
    deposit_amount = DecimalField(
        _l('Security Deposit Amount (KSh)'),
        validators=[Optional(), NumberRange(min=0, message=_l('Deposit cannot be negative.'))],
        places=2,
        render_kw={"placeholder": _l("e.g., 20000.00")}
    )
    deposit_policy = TextAreaField(
        _l('Security Deposit Policy (Optional)'),
        validators=[Optional(), Length(max=500, message=_l('Policy text too long.'))],
        render_kw={"rows": 3, "placeholder": _l("e.g., Refundable within 30 days of vacation, less damages.")}
    )
    submit = SubmitField(_l('Save Property'))

class RecordPaymentForm(FlaskForm):
    tenant_id = SelectField(
        _l('Tenant'),
        validators=[DataRequired(_l('Tenant selection is required.'))],
        coerce=int,
        choices=[],
        render_kw={"class": "form-select"}
    )
    amount = DecimalField(
        _l('Amount Paid (KSh)'),
        validators=[
            DataRequired(_l('Amount is required.')),
            NumberRange(min=0.01, message=_l('Amount must be greater than 0.'))
        ],
        places=2,
        render_kw={"placeholder": _l("e.g., 15000.00")}
    )
    payment_date = DateField(
        _l('Payment Date'),
        validators=[DataRequired(_l('Payment date is required.'))],
        format='%Y-%m-%d',
        render_kw={"placeholder": "YYYY-MM-DD"}
    )
    payment_method = SelectField(
        _l('Payment Method'),
        validators=[DataRequired(_l('Payment method is required.'))],
        choices=[
            ('', _l('Select Method...')),
            ('M-Pesa', _l('M-Pesa')),
            ('Cash', _l('Cash')),
            ('Bank Transfer', _l('Bank Transfer')),
            ('Other', _l('Other'))
        ],
        render_kw={"class": "form-select"}
    )
    transaction_id = StringField(
        _l('M-Pesa Transaction ID (Optional)'),
        validators=[
            Optional(),
            Length(max=100, message=_l('Transaction ID cannot exceed 100 characters.'))
        ],
        render_kw={"placeholder": _l("e.g., RA123ABCDEF")}
    )
    description = TextAreaField(
        _l('Description (Optional)'),
        validators=[Length(max=255, message=_l('Description cannot exceed 255 characters.'))],
        render_kw={"rows": 3, "placeholder": _l("Any additional notes about this payment")}
    )
    is_offline = BooleanField(_l('Record as Offline Payment (Sync later)'))
    offline_reference = StringField(
        _l('Offline Reference (Optional)'),
        validators=[Optional(), Length(max=100, message=_l('Reference cannot exceed 100 characters.'))],
        render_kw={"placeholder": _l("e.g., Manual Receipt #123")}
    )
    submit = SubmitField(_l('Record Payment'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from flask_security import current_user
            if current_user.is_authenticated and hasattr(current_user, 'has_role') and current_user.has_role('landlord'):
                property_ids = [p.id for p in Property.query.filter_by(landlord_id=current_user.id).all()]
                tenants = Tenant.query.filter(Tenant.property_id.in_(property_ids)).order_by(Tenant.first_name).all()
                self.tenant_id.choices = [
                    (t.id, _l(f"{t.first_name} {t.last_name} ({t.property.name})"))
                    for t in tenants
                ]
            else:
                self.tenant_id.choices = []
        except Exception as e:
            current_app.logger.error(f"Error populating tenant choices for RecordPaymentForm: {e}")
            self.tenant_id.choices = []
        if not self.tenant_id.choices or self.tenant_id.choices[0][0] != 0:
            self.tenant_id.choices.insert(0, (0, _l('Select a Tenant...')))

    def validate_tenant_id(self, field):
        if field.data == 0:
            raise ValidationError(_l('Please select a tenant.'))

    def validate_transaction_id(self, field):
        if self.payment_method.data == 'M-Pesa' and not field.data:
            raise ValidationError(_l('M-Pesa Transaction ID is required for M-Pesa payments.'))

    def validate_offline_reference(self, field):
        if self.is_offline.data and not field.data:
            raise ValidationError(_l('Offline reference is required for offline payments.'))

class ExtendedEditProfileForm(FlaskForm):
    username = StringField(
        _l('Username'),
        validators=[DataRequired(_l('Username is required')), Length(min=2, max=20)]
    )
    first_name = StringField(
        _l('First Name'),
        validators=[DataRequired(_l('First name is required.')), Length(min=2, max=50)]
    )
    email = StringField(
        _l('Email'),
        validators=[DataRequired(_l('Email is required.')), Length(min=2, max=50)]
    )
    phone_number = TelField(
        _l('Phone Number'),
        validators=[Optional(), Length(min=10, max=15, message=_l('Phone number must be between 10 and 15 digits.'))]
    )
    county = StringField(
        _l('County'),
        validators=[DataRequired(_l('County is required.')), Length(min=2, max=100)]
    )
    language = SelectField(
        _l('Language'),
        validators=[Optional()],
        choices=[
            ('', _l('Select Language...')),
            ('en', _l('English')),
            ('sw', _l('Swahili'))
        ],
        render_kw={"class": "form-select"}
    )
    roles = SelectMultipleField(
        _l('Roles'),
        coerce=int,  # Assuming role IDs are integers
        validators=[Optional()],
        render_kw={"class": "form-select"}
    )
    submit = SubmitField(_l('Update Profile'))

    def validate_phone_number(self, field):
        if field.data:
            digits_only = ''.join(filter(str.isdigit, field.data))
            if len(digits_only) < 10:
                raise ValidationError(_l('Phone number must contain at least 10 digits.'))
            field.data = digits_only
class TenantPaymentForm(FlaskForm):
    amount = DecimalField("Amount", validators=[DataRequired(), NumberRange(min=1)], places=2)
    payment_method = SelectField("Payment Method", choices=[("mpesa", "M-Pesa"), ("bank", "Bank"), ("cash", "Cash")], validators=[DataRequired()])
    transaction_id = StringField("Transaction ID", validators=[Optional()])
    paybill_number = StringField("PayBill Number", validators=[Optional()])
    payment_date = DateField("Payment Date", validators=[DataRequired()])
    fees = DecimalField("Transaction Fees", validators=[Optional()], places=2)
    description = TextAreaField("Description (optional)")
    is_offline = BooleanField("Is this an offline payment?")
    offline_reference = StringField("Offline Reference (optional)")


class ReportFilterForm(FlaskForm):
    property_id = SelectField('Property', choices=[('', 'All Properties')], coerce=str)
    start_date = DateField('Start Date', validators=[DataRequired()], format='%Y-%m-%d')
    end_date = DateField('End Date', validators=[DataRequired()], format='%Y-%m-%d')
    submit = SubmitField('Generate Report')

class AssignPropertyForm(FlaskForm):
    tenant_id = SelectField(
        _l('Select Tenant'),
        coerce=int,
        validators=[DataRequired()],
        render_kw={"class": "form-select"}
    )

    property_id = SelectField(
        _l('Select Property'),
        choices=[...],
        coerce=int,
        validators=[DataRequired()],
        render_kw={"class": "form-select"}
    )

    unit_id = IntegerField(
        _l('Select Unit'),
        
        validators=[DataRequired()],
        render_kw={"class": "form-select"}
    )

    submit = SubmitField(_l('Assign Property'), render_kw={"class": "btn btn-primary w-100"})

class DeleteTenantForm(FlaskForm):
    submit = SubmitField('Delete')
