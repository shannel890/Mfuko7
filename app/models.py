from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey
from flask_security.models import sqla


class Model(DeclarativeBase):
    pass

sqla.FsModels.set_db_info(base_model=Model)


class Role(Model, sqla.FsRoleMixin):
    __tablename__ = 'role'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    description: Mapped[str] = None


class User(Model, sqla.FsUserMixin):
    __tablename__ = 'user'
    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]

    # A user can own many properties
    properties: Mapped[list["Property"]] = relationship(back_populates="landlord_user")


class Tenant(Model):
    __tablename__ = 'tenant'
    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]
    status: Mapped[str]
    due_day_of_month: Mapped[int] = None
    grace_period_days: Mapped[int] = None
    lease_start_date: Mapped[str] = None
    lease_end_date: Mapped[str] = None

    # Foreign key to property
    property_id: Mapped[int] = mapped_column(ForeignKey("property.id"))
    property: Mapped["Property"] = relationship(back_populates="tenants")

    # One tenant can have many payments
    payments: Mapped[list["Payment"]] = relationship(back_populates="tenant")


class Property(Model):
    __tablename__ = 'property'
    id: Mapped[int] = mapped_column(primary_key=True)

    landlord_id: Mapped[int] = mapped_column(ForeignKey("user.id"))  # FK to User
    landlord_user: Mapped["User"] = relationship(back_populates="properties")

    created_at: Mapped[str] = None
    updated_at: Mapped[str] = None
    county: Mapped[str] = None
    amenities: Mapped[str] = None
    utility_bill: Mapped[str] = None
    deposit_amount: Mapped[float] = None
    deposit_policy: Mapped[str] = None

    # One property can have many tenants
    tenants: Mapped[list["Tenant"]] = relationship(back_populates="property")


class Payment(Model):
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


class County(Model):
    __tablename__ = 'county'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    state: Mapped[str] = None
    country: Mapped[str] = None
    created_at: Mapped[str] = None
    updated_at: Mapped[str] = None
