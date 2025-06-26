from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey
from flask_security.models import sqla
from datetime import datetime
from app.extensions import db
from sqlalchemy import ForeignKey, String, Integer, Float, Text
class Model(DeclarativeBase):
    pass

sqla.FsModels.set_db_info(base_model=Model)

roles_users = db.Table(
    'roles_users',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'))
)

class Role(db.Model, sqla.FsRoleMixin):
    __tablename__ = 'role'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    description: Mapped[str] = mapped_column(nullable=True)


class User(db.Model, sqla.FsUserMixin):
    __tablename__ = 'user'
    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
    password: Mapped[str]
    confirm_password: Mapped[str] = mapped_column(nullable=True)
    active: Mapped[bool] = mapped_column(default=True)     
    fs_uniquifier: Mapped[str] = mapped_column(unique=True, nullable=False)
    # A user can own many properties
    properties: Mapped[list["Property"]] = relationship(back_populates="landlord_user")


class Tenant(db.Model):
    __tablename__ = 'tenant'

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]
    status: Mapped[str]
    due_day_of_month: Mapped[int]
    grace_period_days: Mapped[int]
    lease_start_date: Mapped[str]
    lease_end_date: Mapped[str]

    property_id: Mapped[int] = mapped_column(ForeignKey("property.id"))
    property: Mapped["Property"] = relationship(back_populates="tenants")

    payments: Mapped[list["Payment"]] = relationship(back_populates="tenant")

class Property(db.Model):
    __tablename__ = 'property'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    property_type: Mapped[str] = mapped_column(String(50), nullable=False)
    number_of_units: Mapped[int] = mapped_column(Integer, nullable=False)

    landlord_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    landlord_user: Mapped["User"] = relationship(back_populates="properties")

    county: Mapped[str] = mapped_column(String(100), nullable=False)
    amenities: Mapped[str] = mapped_column(Text, nullable=True)
    utility_bill: Mapped[str] = mapped_column(Text, nullable=True)
    deposit_amount: Mapped[float] = mapped_column(Float, nullable=True)
    deposit_policy: Mapped[str] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tenants: Mapped[list["Tenant"]] = relationship(back_populates="property")

class Payment(db.Model):
    __tablename__ = 'payment'
    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id"))  # FK to Tenant
    tenant: Mapped["Tenant"] = relationship(back_populates="payments")

    amount: Mapped[float]
    payment_date: Mapped[str]
    status: Mapped[str] = None
    payment_method: Mapped[str] = None
    transaction_id: Mapped[str] = None
    notes: Mapped[str] = None
    created_at: Mapped[str] = None
    updated_at: Mapped[str] = None


class County(db.Model):
    __tablename__ = 'county'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    state: Mapped[str] = None
    country: Mapped[str] = None
    created_at: Mapped[str] = None
    updated_at: Mapped[str] = None
