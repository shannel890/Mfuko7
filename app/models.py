from app.extensions import db
from flask_login import UserMixin
from datetime import datetime, timezone
import json # For handling JSON serialized fields



# Define the many-to-many relationship table for users and roles
# Flask-Security-Too expects this structure for Role and User models
class UserRoles(db.Model):
    __tablename__ = 'user_roles'
    id = db.Column(db.Integer(), primary_key=True)
    # Added ondelete='CASCADE' for better database integrity
    user_id = db.Column(db.Integer(), db.ForeignKey('user.id', ondelete='CASCADE'))
    role_id = db.Column(db.Integer(), db.ForeignKey('role.id', ondelete='CASCADE'))

roles_users = db.Table('roles_users',
    db.Column('user_id', db.Integer(), db.ForeignKey('user.id')),
    db.Column('role_id', db.Integer(), db.ForeignKey('role.id')))
# Define Role model
class Role(db.Model):
    __tablename__ = 'role'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    description = db.Column(db.String(255))
    # Removed: users = db.relationship('User', secondary='user_roles')
    # The 'users' backref is created implicitly by the 'roles' relationship in the User model.

# Define User model
class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False) # Store hashed password
    active = db.Column(db.Boolean(), default=True)
    fs_uniquifier = db.Column(db.String(64), unique=True, nullable=False) # Required by Flask-Security-Too
    confirmed_at = db.Column(db.DateTime())
    last_login_at = db.Column(db.DateTime())
    current_login_at = db.Column(db.DateTime())
    last_login_ip = db.Column(db.String(100))
    current_login_ip = db.Column(db.String(100))
    login_count = db.Column(db.Integer)

    # Custom fields for REPT application
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    us_phone_number = db.Column(db.String(20)) # Renamed from 'phone_number' for clarity

    # Relationship to County model (Many-to-one: Many users can be in one county)
    county_id = db.Column(db.Integer, db.ForeignKey('county.id'), nullable=True)
    county = db.relationship('County', backref='users') # Creates 'users' backref on County model

    # Language preference for Babel
    language = db.Column(db.String(10), default='en')

    # Notification preferences (e.g., JSON string)
    notification_preferences = db.Column(db.Text, default='{}')

    # Relationship to roles
    # This creates the 'users' backref on the Role model.
    roles = db.relationship('Role', secondary='roles_users',
                            backref=db.backref('users', lazy='dynamic'))

    # One-to-many relationship with Property (Landlord owns many properties)
    properties = db.relationship('Property', backref='landlord_user', lazy=True) # Renamed backref for clarity

    # One-to-one relationship with Tenant (User can be a tenant)
    tenant_profile = db.relationship('Tenant', uselist=False, backref='user_account', cascade="all, delete-orphan") # Added cascade

    # One-to-many relationship with Payments (User can make/receive many payments)
    payments_received = db.Column(db.Numeric(10, 2), default=0.00) # Track total payments received
    payments_made = db.relationship('Payment', backref='payer', lazy=True) # Assuming user is the one making payment

    # One-to-many relationship with AuditLog (User actions are logged)
    audit_logs = db.relationship('AuditLog', backref='user_logger', lazy=True) # Renamed backref for clarity


    def __repr__(self):
        return f'<User {self.email}>'

    # Methods required by Flask-Login (part of Flask-Security-Too)
    def get_id(self):
        return str(self.id)

    def is_active(self):
        return self.active

    def is_authenticated(self):
        return True

    def is_anonymous(self):
        return False

    # Helper method to check roles
    def has_role(self, role):
        # Ensure role is a string and matches name attribute
        return any(r.name == role for r in self.roles)

    # Property to handle JSON-serialized preferences
    @property
    def prefs(self):
        if self.notification_preferences:
            return json.loads(self.notification_preferences)
        return {}

    @prefs.setter
    def prefs(self, value):
        self.notification_preferences = json.dumps(value)


# Define County model
class County(db.Model):
    __tablename__ = 'county'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    # The 'users' backref is created by the User model's county relationship

    # Added these fields for consistency and potential future use, based on your previous model style
    state = db.Column(db.String(100), nullable=True) # Assuming 'state' for larger regions if applicable
    country = db.Column(db.String(100), nullable=True) # Assuming 'country' for larger regions if applicable

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<County {self.name}>'

# Define Property model
class Property(db.Model):
    __tablename__ = 'property'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    property_type = db.Column(db.String(50), nullable=False) # e.g., 'residential', 'commercial', 'apartment'
    number_of_units = db.Column(db.Integer, nullable=False, default=1)

    # Foreign key to User (Landlord)
    landlord_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # 'landlord_user' backref is created from the User model's properties relationship

    # Additional fields based on your provided structure
    county_name = db.Column(db.String(100), nullable=False) # Storing county name directly for simplicity if not a FK
    # If you want this to be a foreign key to the County model, it should be county_id
    # county_id = db.Column(db.Integer, db.ForeignKey('county.id'))
    # county = db.relationship('County', backref='properties') # if FK

    amenities = db.Column(db.Text, nullable=True) # Stored as JSON string or comma-separated
    utility_bill = db.Column(db.Text, nullable=True) # Stored as JSON string for utility details
    deposit_amount = db.Column(db.Numeric(10, 2), nullable=True)
    deposit_policy = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    tenants = db.relationship('Tenant', backref='property_rel', lazy=True, cascade="all, delete-orphan") # Renamed backref and added cascade

    def __repr__(self):
        return f'<Property {self.name}>'


# Define Tenant model
class Tenant(db.Model):
    __tablename__ = 'tenant'
    id = db.Column(db.Integer, primary_key=True)

    # Foreign key to User, if the tenant is also a user in the system
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=True)
    # 'user_account' backref is created from the User model's tenant_profile relationship

    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    phone_number = db.Column(db.String(20))
    status = db.Column(db.String(50), default='active') # e.g., 'active', 'inactive', 'evicted'
    due_day_of_month = db.Column(db.Integer) # Day of month rent is due (e.g., 1st, 5th)
    grace_period_days = db.Column(db.Integer, default=5) # Number of grace days for rent payment
    lease_start_date = db.Column(db.Date)
    lease_end_date = db.Column(db.Date)

    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=False)
    # 'property_rel' backref is created from the Property model's tenants relationship

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    payments = db.relationship('Payment', backref='tenant_payer', lazy=True, cascade="all, delete-orphan") # Renamed backref and added cascade
    # One-to-one relationship with Unit (handled in Unit model as current_tenant)


    def __repr__(self):
        return f'<Tenant {self.first_name} {self.last_name}>'

# Define Payment model
class Payment(db.Model):
    __tablename__ = 'payment'
    id = db.Column(db.Integer, primary_key=True)

    tenant_id = db.Column(db.Integer, db.ForeignKey("tenant.id"), nullable=False)
    # 'tenant_payer' backref created from the Tenant model's payments relationship

    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(50), default='completed') # e.g., 'completed', 'pending', 'failed'
    payment_method = db.Column(db.String(50), nullable=True) # e.g., 'M-Pesa', 'Bank Transfer', 'Cash'
    transaction_id = db.Column(db.String(100), unique=True, nullable=True) # M-Pesa transaction ID
    notes = db.Column(db.Text, nullable=True)

    # Added for consistency
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship to Invoice (if payment is linked to a specific invoice)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=True)
    invoice_rel = db.relationship('Invoice', backref='payments', lazy=True) # Renamed for clarity

    # Foreign key to User (payer, if a registered user made the payment directly)
    payer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    # 'payer' backref is created from the User model's payments_made relationship

    def __repr__(self):
        return f'<Payment {self.amount} on {self.payment_date.strftime("%Y-%m-%d")}>'


# Define Invoice model (New model based on previous context)
class Invoice(db.Model):
    __tablename__ = 'invoice'
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(100), unique=True, nullable=False)
    issue_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    due_date = db.Column(db.Date, nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    amount_due = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(50), default='pending') # e.g., 'pending', 'paid', 'overdue', 'partially_paid'
    description = db.Column(db.Text, nullable=True)

    # Foreign key to Unit (the unit for which this invoice is generated) - assuming units exist
    # If a property has units, invoices are typically for units.
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'), nullable=True)
    unit = db.relationship('Unit', backref='invoices', lazy=True)

    # Foreign key to Tenant (the tenant receiving this invoice)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    tenant_invoice = db.relationship('Tenant', foreign_keys=[tenant_id], backref='invoices_received', lazy=True)


    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Invoice {self.invoice_number} - {self.status}>'

# Define Unit model (Added back based on common real estate structure and invoice FK)
class Unit(db.Model):
    __tablename__ = 'unit'
    id = db.Column(db.Integer, primary_key=True)
    unit_number = db.Column(db.String(50), nullable=False)
    rent_amount = db.Column(db.Numeric(10, 2), nullable=False)
    deposit_amount = db.Column(db.Numeric(10, 2), nullable=True)
    bedrooms = db.Column(db.Integer, nullable=True)
    bathrooms = db.Column(db.Integer, nullable=True)
    size_sqft = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(50), default='vacant') # e.g., 'occupied', 'vacant', 'maintenance'
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Foreign key to Property
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=False)
    # 'property_rel' backref created from Property model's units_rel relationship

    # One-to-one relationship with Tenant (a unit has one current tenant)
    # This foreign key is on the Unit side, pointing to the Tenant who occupies it
    current_tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), unique=True, nullable=True)
    # The backref 'unit_occupied' is now created in the Tenant model explicitly if needed
    current_tenant = db.relationship('Tenant', foreign_keys=[current_tenant_id], uselist=False, post_update=True)


    def __repr__(self):
        return f'<Unit {self.unit_number} (Property ID: {self.property_id})>'


# Define AuditLog model (New model based on previous context)
class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # User who performed the action
    action = db.Column(db.String(255), nullable=False) # e.g., 'user_login', 'property_created', 'payment_recorded'
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    details = db.Column(db.Text, nullable=True) # JSON string of relevant details

    # 'user_logger' backref created from the User model's audit_logs relationship

    def __repr__(self):
        return f'<AuditLog {self.action} by User {self.user_id} at {self.timestamp}>'