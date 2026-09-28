from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import (
    Tenant,
    Payment,
    Invoice,
    Property,
    Unit,
)


def _money(value):
    if value is None:
        return 0.0

    if isinstance(value, Decimal):
        return float(value)

    return float(value)


def get_rent_balance(user):
    """
    Return the authenticated tenant's current rent information.

    IMPORTANT:
    We use the authenticated Flask user instead of accepting a tenant_id
    supplied by the AI or user.
    """

    tenant = Tenant.query.filter_by(user_id=user.id).first()

    if not tenant:
        return {
            "success": False,
            "message": "No tenant profile is associated with this account."
        }

    total_paid = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(
            Payment.tenant_id == tenant.id,
            Payment.status == "confirmed"
        )
        .scalar()
    )

    # Current invoice balance, when available.
    current_invoice = (
        Invoice.query
        .filter_by(tenant_id=tenant.id)
        .order_by(Invoice.issue_date.desc())
        .first()
    )

    property_name = None
    unit_number = None

    if tenant.property:
        property_name = tenant.property.name

    if tenant.unit:
        unit_number = tenant.unit.unit_number

    return {
        "success": True,
        "tenant": {
            "name": f"{tenant.first_name} {tenant.last_name}",
            "status": tenant.status,
        },
        "property": property_name,
        "unit": unit_number,
        "monthly_rent": _money(tenant.rent_amount),
        "due_day": tenant.due_day_of_month,
        "grace_period_days": tenant.grace_period_days,
        "total_confirmed_payments": _money(total_paid),
        "current_invoice": (
            {
                "invoice_number": current_invoice.invoice_number,
                "total_amount": _money(current_invoice.total_amount),
                "amount_due": _money(current_invoice.amount_due),
                "status": current_invoice.status,
            }
            if current_invoice
            else None
        ),
    }


def get_payment_history(user, limit=10):
    """
    Return payment history belonging only to the authenticated tenant.
    """

    tenant = Tenant.query.filter_by(user_id=user.id).first()

    if not tenant:
        return {
            "success": False,
            "message": "No tenant profile is associated with this account."
        }

    try:
        limit = max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        limit = 10

    payments = (
        Payment.query
        .filter_by(tenant_id=tenant.id)
        .order_by(Payment.payment_date.desc())
        .limit(limit)
        .all()
    )

    return {
        "success": True,
        "payments": [
            {
                "amount": _money(payment.amount),
                "date": (
                    payment.payment_date.isoformat()
                    if payment.payment_date
                    else None
                ),
                "status": payment.status,
                "payment_method": payment.payment_method,
                "transaction_id": payment.transaction_id,
                "description": payment.description,
            }
            for payment in payments
        ],
    }


def search_properties(
    county=None,
    property_type=None,
    max_rent=None,
    bedrooms=None,
):
    """
    Search available units.

    This tool only exposes units that are currently marked as vacant.
    """

    query = (
        db.session.query(Unit, Property)
        .join(Property, Unit.property_id == Property.id)
        .filter(Unit.status == "vacant")
    )

    if county:
        query = query.filter(
            Property.county_name.ilike(f"%{county}%")
        )

    if property_type:
        query = query.filter(
            Property.property_type.ilike(f"%{property_type}%")
        )

    if max_rent is not None:
        try:
            query = query.filter(
                Unit.rent_amount <= float(max_rent)
            )
        except (TypeError, ValueError):
            pass

    if bedrooms is not None:
        try:
            query = query.filter(
                Unit.bedrooms == int(bedrooms)
            )
        except (TypeError, ValueError):
            pass

    results = query.limit(20).all()

    return {
        "success": True,
        "properties": [
            {
                "property_id": property.id,
                "property_name": property.name,
                "address": property.address,
                "county": property.county_name,
                "property_type": property.property_type,
                "unit_number": unit.unit_number,
                "rent_amount": _money(unit.rent_amount),
                "bedrooms": unit.bedrooms,
                "bathrooms": unit.bathrooms,
                "size_sqft": unit.size_sqft,
                "deposit_amount": _money(unit.deposit_amount),
                "amenities": property.amenities_list,
            }
            for unit, property in results
        ],
    }