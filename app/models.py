from app.extensions import db
from flask_login import UserMixin
from datetime import datetime, timezone, timedelta
import json
#from app.utils.constrants import UserRoles

roles_users = db.Table('roles_users',
    db.Column('user_id', db.Integer(), db.ForeignKey('user.id', ondelete='CASCADE')),
    db.Column('role_id', db.Integer(), db.ForeignKey('role.id', ondelete='CASCADE')),
    db.Index('ix_roles_users_user_id', 'user_id'),
    db.Index('ix_roles_users_role_id', 'role_id')
)

class Role(db.Model):
    __tablename__ = 'role'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))

    def __repr__(self):
        return f'<Role {self.name}>'

class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=True)
    role = db.Column(db.String, nullable=False)
    is_oauth_user = db.Column(db.Boolean, default=False, nullable=False) 
    active = db.Column(db.Boolean(), default=True)
    fs_uniquifier = db.Column(db.String(64), unique=True, nullable=False)
    confirmed_at = db.Column(db.DateTime)
    last_login_at = db.Column(db.DateTime)
    current_login_at = db.Column(db.DateTime)
    last_login_ip = db.Column(db.String(100))
    current_login_ip = db.Column(db.String(100))
    login_count = db.Column(db.Integer)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    phone_number = db.Column(db.String(20))
    county_id = db.Column(db.Integer, db.ForeignKey('county.id', ondelete='SET NULL'), nullable=True)
    county = db.relationship('County', backref='users')
    language = db.Column(db.String(10), default='en')
    notification_preferences = db.Column(db.Text, default='{}')
    roles = db.relationship('Role', secondary='roles_users', backref=db.backref('users', lazy='dynamic'))
    properties = db.relationship('Property', backref='landlord', lazy=True)
    tenant_profile = db.relationship('Tenant', uselist=False, backref='user', cascade="all, delete-orphan", foreign_keys='Tenant.user_id')
    payments_made = db.relationship('Payment', backref='payer', lazy=True)
    audit_logs = db.relationship('AuditLog', backref='user', lazy=True)

    @property
    def prefs(self):
        try:
            return json.loads(self.notification_preferences) if self.notification_preferences else {}
        except json.JSONDecodeError:
            return {}
    def has_role(self, role_name: str):
        return any(role.name.lower() == role_name.lower() for role in self.roles)

    @prefs.setter
    def prefs(self, value):
        self.notification_preferences = json.dumps(value)

    
    def __repr__(self):
        return f'<User {self.email}>'

class County(db.Model):
    __tablename__ = 'county'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    state = db.Column(db.String(100), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<County {self.name}>'

class Property(db.Model):
    __tablename__ = 'property'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    payment_method = db.Column(db.String(20), nullable=True)
    transaction_id = db.Column(db.String(120), nullable=True)  
    paybill_number = db.Column(db.String(20), nullable=True)  
    fees = db.Column(db.Numeric(10, 2), nullable=True)  
    tenants = db.relationship('Tenant', back_populates='property', cascade="all, delete-orphan", lazy=True)

    status = db.Column(db.String(20), default='pending')
    property_type = db.Column(db.String(50), nullable=False)
    number_of_units = db.Column(db.Integer, nullable=False, default=1)
    landlord_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    county_name = db.Column(db.String(100), nullable=False)
    amenities = db.Column(db.Text, nullable=True)
    utility_bill_types = db.Column(db.Text, nullable=True)
    unit_numbers = db.Column(db.Text, nullable=False)
    deposit_amount = db.Column(db.Numeric(10, 2), nullable=True)
    deposit_policy = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    units = db.relationship('Unit', back_populates='property', lazy=True)  # 🔄 Use back_populates here
    @property
    def amenities_list(self):
        try:
            return json.loads(self.amenities) if self.amenities else []
        except json.JSONDecodeError:
            return self.amenities.split(',') if self.amenities else []

    @amenities_list.setter
    def amenities_list(self, value):
        self.amenities = json.dumps(value)

    @property
    def utility_bill_list(self):
        try:
            return json.loads(self.utility_bill_types) if self.utility_bill_types else []
        except json.JSONDecodeError:
            return self.utility_bill_types.split(',') if self.utility_bill_types else []

    @utility_bill_list.setter
    def utility_bill_list(self, value):
        self.utility_bill_types = json.dumps(value)

    def __repr__(self):
        return f'<Property {self.name}>'

class Tenant(db.Model):
    __tablename__ = 'tenant'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), unique=True, nullable=True, index=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    phone_number = db.Column(db.String(20))
    property = db.relationship('Property', back_populates='tenants')
    rent_amount = db.Column(db.Numeric(10, 2), nullable=True, default=0.00)  
    national_id = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(50), default='active')
    due_day_of_month = db.Column(db.Integer)
    grace_period_days = db.Column(db.Integer, default=5)
    lease_start_date = db.Column(db.Date)
    lease_end_date = db.Column(db.Date)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id', ondelete='CASCADE'), nullable=True, index=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id', ondelete='CASCADE'), nullable=True, index=True)
    landlord_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    landlord = db.relationship('User', backref='tenants', foreign_keys=[landlord_id])
    unit = db.relationship('Unit', foreign_keys=[unit_id], backref='tenant', uselist=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    payments = db.relationship('Payment', backref='tenant', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Tenant {self.first_name} {self.last_name}>'

class Unit(db.Model):
    __tablename__ = 'unit'

    id = db.Column(db.Integer, primary_key=True)
    unit_number = db.Column(db.String(50), nullable=False)
    rent_amount = db.Column(db.Numeric(10, 2), nullable=False)
    deposit_amount = db.Column(db.Numeric(10, 2), nullable=True)
    bedrooms = db.Column(db.Integer, nullable=True)
    bathrooms = db.Column(db.Integer, nullable=True)
    size_sqft = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(50), default='vacant')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True) 
    property_id = db.Column(db.Integer, db.ForeignKey('property.id', ondelete='CASCADE'), nullable=False, index=True)

    property = db.relationship('Property', back_populates='units')  # 🔄 Use back_populates here

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


    def __repr__(self):
        return f'<Unit {self.unit_number}>'

class Payment(db.Model):
    __tablename__ = 'payment'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100)) 
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(50), default='confirmed')
    payment_method = db.Column(db.String(50), nullable=False)
    transaction_id = db.Column(db.String(100), unique=True, nullable=True)
    is_offline = db.Column(db.Boolean, default=False)
    offline_reference = db.Column(db.String(100), nullable=True)  
    description = db.Column(db.String(255))
    notes = db.Column(db.Text, nullable=True)
    paybill_number = db.Column(db.String(20))
    fees = db.Column(db.Numeric(10, 2))
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id', ondelete='SET NULL'), nullable=True)
    invoice = db.relationship('Invoice', backref='payments', lazy=True)
    payer_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    

    def __repr__(self):
        return f'<Payment {self.amount} on {self.payment_date.strftime("%Y-%m-%d")}>'

class Invoice(db.Model):
    __tablename__ = 'invoice'
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(100), unique=True, nullable=False)
    issue_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    due_date = db.Column(db.Date, nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    amount_due = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(50), default='pending')
    description = db.Column(db.Text, nullable=True)
    is_offline = db.Column(db.Boolean, default=False)
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id', ondelete='SET NULL'), nullable=True)
    unit = db.relationship('Unit', backref='invoices', lazy=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False, index=True)
    tenant = db.relationship('Tenant', foreign_keys=[tenant_id], backref='invoices', lazy=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Invoice {self.invoice_number}>'

class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    action = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    details = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<AuditLog {self.action} by User {self.user_id} at {self.timestamp}>'