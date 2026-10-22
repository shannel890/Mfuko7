from decimal import Decimal

from sqlalchemy import func
from app.services.payment_service import PaymentService
from app.extensions import db
from app.models import (
    User,
    Tenant,
    Payment,
    Invoice,
    Property,
    Unit,
    Issue,
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


def get_current_invoice(user):
    """
    Return the authenticated tenant's latest invoice.
    """

    tenant = Tenant.query.filter_by(
        user_id=user.id
    ).first()

    if not tenant:
        return {
            "success": False,
            "message": "No tenant profile is associated with this account."
        }

    invoice = (
        Invoice.query
        .filter_by(tenant_id=tenant.id)
        .order_by(Invoice.issue_date.desc())
        .first()
    )

    if not invoice:
        return {
            "success": False,
            "message": "No invoice was found for your account."
        }

    return {
        "success": True,
        "invoice": {
            "invoice_number": invoice.invoice_number,
            "issue_date": (
                invoice.issue_date.isoformat()
                if invoice.issue_date
                else None
            ),
            "total_amount": _money(invoice.total_amount),
            "amount_due": _money(invoice.amount_due),
            "status": invoice.status,
            "description": invoice.description,
        }
    }

def get_my_property_info(user):
    """
    Return the authenticated tenant's property, unit, and lease information.
    """
    tenant = Tenant.query.filter_by(user_id=user.id).first()

    if not tenant:
        return {
            "success": False,
            "message": "No tenant profile was found for this account."
        }

    property_obj = tenant.property
    unit = tenant.unit

    if not property_obj:
        return {
            "success": False,
            "message": "No property is currently associated with your tenant account."
        }

    result = {
        "success": True,
        "property": {
            "name": property_obj.name,
            "address": property_obj.address,
            "county": property_obj.county_name,
            "property_type": property_obj.property_type,
        },
        "unit": None,
        "lease": {
            "start_date": (
                tenant.lease_start_date.isoformat()
                if tenant.lease_start_date else None
            ),
            "end_date": (
                tenant.lease_end_date.isoformat()
                if tenant.lease_end_date else None
            ),
            "due_day_of_month": tenant.due_day_of_month,
            "grace_period_days": tenant.grace_period_days,
        },
    }

    if unit:
        result["unit"] = {
            "unit_number": unit.unit_number,
            "monthly_rent": float(unit.rent_amount or 0),
            "bedrooms": unit.bedrooms,
            "bathrooms": unit.bathrooms,
            "size_sqft": unit.size_sqft,
            "status": unit.status,
        }

    return result

def get_lease_details(user):
    """
    Return the authenticated tenant's lease dates and rent-payment schedule.
    """
    tenant = Tenant.query.filter_by(user_id=user.id).first()

    if not tenant:
        return {
            "success": False,
            "message": "No tenant profile was found for this account."
        }

    return {
        "success": True,
        "lease_start_date": (
            tenant.lease_start_date.isoformat()
            if tenant.lease_start_date else None
        ),
        "lease_end_date": (
            tenant.lease_end_date.isoformat()
            if tenant.lease_end_date else None
        ),
        "rent_due_day": tenant.due_day_of_month,
        "grace_period_days": tenant.grace_period_days,
        "monthly_rent": float(tenant.rent_amount or 0),
        "tenant_status": tenant.status,
    }

def get_landlord_info(user):
    """
    Return the authenticated tenant's landlord/property manager information.
    """
    tenant = Tenant.query.filter_by(user_id=user.id).first()

    if not tenant:
        return {
            "success": False,
            "message": "No tenant profile was found for this account."
        }

    if not tenant.landlord_id:
        return {
            "success": False,
            "message": "No landlord is currently associated with your tenant account."
        }

    landlord = User.query.get(tenant.landlord_id)

    if not landlord:
        return {
            "success": False,
            "message": "The landlord associated with your account could not be found."
        }

    return {
        "success": True,
        "landlord": {
            "name": " ".join(
                part for part in [landlord.first_name, landlord.last_name]
                if part
            ) or landlord.username,
            "email": landlord.email,
            "phone_number": landlord.phone_number,
        }
    }

def get_tenant_account_summary(user):
    """
    Return a consolidated summary of the authenticated tenant's account.
    """
    tenant = Tenant.query.filter_by(user_id=user.id).first()

    if not tenant:
        return {
            "success": False,
            "message": "No tenant profile was found for this account."
        }

    property_obj = tenant.property
    unit = tenant.unit

    landlord = None
    if tenant.landlord_id:
        landlord = User.query.get(tenant.landlord_id)

    maintenance_requests = (
        Issue.query
        .filter_by(tenant_id=user.id)
        .order_by(Issue.created_at.desc())
        .limit(5)
        .all()
    )

    summary = {
        "success": True,
        "tenant": {
            "name": f"{tenant.first_name} {tenant.last_name}",
            "status": tenant.status,
        },
        "property": None,
        "unit": None,
        "lease": {
            "start_date": (
                tenant.lease_start_date.isoformat()
                if tenant.lease_start_date else None
            ),
            "end_date": (
                tenant.lease_end_date.isoformat()
                if tenant.lease_end_date else None
            ),
            "rent_due_day": tenant.due_day_of_month,
            "grace_period_days": tenant.grace_period_days,
        },
        "landlord": None,
        "rent_balance": None,
        "maintenance_requests": [],
    }

    if property_obj:
        summary["property"] = {
            "name": property_obj.name,
            "address": property_obj.address,
            "county": property_obj.county_name,
            "property_type": property_obj.property_type,
        }

    if unit:
        summary["unit"] = {
            "unit_number": unit.unit_number,
            "monthly_rent": float(unit.rent_amount or 0),
            "bedrooms": unit.bedrooms,
            "bathrooms": unit.bathrooms,
            "size_sqft": unit.size_sqft,
            "status": unit.status,
        }

    if landlord:
        summary["landlord"] = {
            "name": " ".join(
                part for part in [landlord.first_name, landlord.last_name]
                if part
            ) or landlord.username,
            "email": landlord.email,
            "phone_number": landlord.phone_number,
        }

    rent_balance = get_rent_balance(user)
    summary["rent_balance"] = rent_balance

    for issue in maintenance_requests:
        summary["maintenance_requests"].append({
            "id": issue.id,
            "title": issue.title,
            "status": issue.status,
            "created_at": (
                issue.created_at.isoformat()
                if issue.created_at else None
            ),
        })

    return summary

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

def get_financial_summary(user):
    """
    Return a consolidated financial summary for the authenticated tenant.
    """
    tenant = Tenant.query.filter_by(user_id=user.id).first()

    if not tenant:
        return {
            "success": False,
            "message": "No tenant profile is associated with this account."
        }

    payments = (
        Payment.query
        .filter_by(tenant_id=tenant.id)
        .order_by(Payment.payment_date.desc())
        .all()
    )

    confirmed_payments = [
        payment for payment in payments
        if (payment.status or "").lower() == "confirmed"
    ]

    total_confirmed = sum(
        float(payment.amount or 0)
        for payment in confirmed_payments
    )

    rent_balance = get_rent_balance(user)

    return {
        "success": True,
        "monthly_rent": float(tenant.rent_amount or 0),
        "rent_balance": rent_balance,
        "total_confirmed_payments": total_confirmed,
        "confirmed_payment_count": len(confirmed_payments),
        "latest_payment": (
            {
                "amount": _money(confirmed_payments[0].amount),
                "date": (
                    confirmed_payments[0].payment_date.isoformat()
                    if confirmed_payments[0].payment_date
                    else None
                ),
                "payment_method": confirmed_payments[0].payment_method,
                "transaction_id": confirmed_payments[0].transaction_id,
            }
            if confirmed_payments
            else None
        ),
        "payment_history": [
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
            for payment in payments[:10]
        ],
    }

def prepare_rent_payment(user, amount):
    """
    Prepare an M-Pesa rent payment without initiating STK Push.
    """
    tenant = Tenant.query.filter_by(user_id=user.id).first()

    if not tenant:
        return {
            "success": False,
            "message": "No tenant profile is associated with this account."
        }

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {
            "success": False,
            "message": "Please provide a valid payment amount."
        }

    if amount <= 0:
        return {
            "success": False,
            "message": "Payment amount must be greater than zero."
        }

    current_invoice = (
        Invoice.query
        .filter_by(tenant_id=tenant.id)
        .order_by(Invoice.issue_date.desc())
        .first()
    )

    if current_invoice:
        maximum_payable = float(current_invoice.amount_due or 0)
    else:
        total_paid = (
            db.session.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(
                Payment.tenant_id == tenant.id,
                Payment.status == "confirmed"
            )
            .scalar()
        )

        maximum_payable = max(
            float(tenant.rent_amount or 0) - float(total_paid or 0),
            0
        )

    if maximum_payable <= 0:
        return {
            "success": False,
            "message": "No payable rent amount is currently available."
        }

    if amount > maximum_payable:
        return {
            "success": False,
            "message": (
                f"The requested payment of Ksh {amount:,.2f} "
                f"exceeds the current payable amount of "
                f"Ksh {maximum_payable:,.2f}."
            )
        }

    if not tenant.phone_number:
        return {
            "success": False,
            "message": (
                "No phone number is registered for your tenant account."
            )
        }

    return {
        "success": True,
        "requires_confirmation": True,
        "amount": amount,
        "maximum_payable": maximum_payable,
        "phone_number": tenant.phone_number,
        "message": (
            f"You're about to initiate an M-Pesa payment of "
            f"Ksh {amount:,.2f} to your registered phone number. "
            f"Your current payable rent is Ksh {maximum_payable:,.2f}. "
            "Please explicitly confirm before the payment is initiated."
        ),
    }

def initiate_rent_payment(user, amount, confirmed=False):
    """
    Initiate an M-Pesa STK Push for the authenticated tenant's rent.

    Payment initiation requires explicit confirmation.
    """
    tenant = Tenant.query.filter_by(user_id=user.id).first()

    if not tenant:
        return {
            "success": False,
            "requires_confirmation": False,
            "message": "No tenant profile is associated with this account."
        }

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {
            "success": False,
            "requires_confirmation": False,
            "message": "Please provide a valid payment amount."
        }

    if amount <= 0:
        return {
            "success": False,
            "requires_confirmation": False,
            "message": "Payment amount must be greater than zero."
        }

    current_invoice = (
        Invoice.query
        .filter_by(tenant_id=tenant.id)
        .order_by(Invoice.issue_date.desc())
        .first()
        )

    if current_invoice:
        maximum_payable = float(current_invoice.amount_due or 0)
    else:
        total_paid = (
            db.session.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(
                Payment.tenant_id == tenant.id,
                Payment.status == "confirmed"
            )
            .scalar()
        )

        monthly_rent = float(tenant.rent_amount or 0)
        total_paid = float(total_paid or 0)

        maximum_payable = max(monthly_rent - total_paid, 0)

    if maximum_payable <= 0:
        return {
            "success": False,
            "requires_confirmation": False,
            "message": "No payable rent amount is currently available."
        }

    if amount > maximum_payable:
        return {
            "success": False,
            "requires_confirmation": False,
            "message": (
                f"The requested payment of Ksh {amount:,.2f} "
                f"exceeds the current payable amount of "
                f"Ksh {maximum_payable:,.2f}."
            )
        }

    if not tenant.phone_number:
        return {
            "success": False,
            "requires_confirmation": False,
            "message": (
                "No phone number is registered for your tenant account. "
                "Please update your phone number before initiating an "
                "M-Pesa payment."
            )
        }

    if not confirmed:
        return {
            "success": False,
            "requires_confirmation": True,
            "amount": amount,
            "maximum_payable": maximum_payable,
            "phone_number": tenant.phone_number,
            "message": (
                f"An M-Pesa STK Push will be sent to your registered "
                f"phone number for Ksh {amount:,.2f}. "
                "Please explicitly confirm before I initiate the payment."
            )
        }

    result = PaymentService.initiate_mpesa_payment(
        tenant_id=tenant.id,
        amount=amount,
        phone_number=tenant.phone_number,
        account_reference=f"Rent-{tenant.id}"
    )

    return {
        "success": result.get("success", False),
        "requires_confirmation": False,
        "checkout_id": result.get("checkout_id"),
        "amount": amount,
        "message": result.get(
            "message",
            "Payment request processed."
        )
    }

def get_payment_instructions(user):
    """
    Return payment instructions for the authenticated tenant's property.
    """
    tenant = Tenant.query.filter_by(user_id=user.id).first()

    if not tenant:
        return {
            "success": False,
            "message": "No tenant profile is associated with this account."
        }

    property_obj = tenant.property

    if not property_obj:
        return {
            "success": False,
            "message": "No property is currently associated with your account."
        }

    return {
        "success": True,
        "property_name": property_obj.name,
        "payment_method": property_obj.payment_method,
        "paybill_number": property_obj.paybill_number,
        "fees": _money(property_obj.fees) if property_obj.fees is not None else None,
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

def get_maintenance_requests(user, limit=10):
    """
    Return maintenance requests belonging to the authenticated tenant.
    """

    tenant = Tenant.query.filter_by(
        user_id=user.id
    ).first()

    if not tenant:
        return {
            "success": False,
            "message": "No tenant profile is associated with this account."
        }

    try:
        limit = max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        limit = 10

    issues = (
        Issue.query
        .filter_by(tenant_id=user.id)
        .order_by(Issue.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "success": True,
        "requests": [
            {
                "id": issue.id,
                "title": issue.title,
                "description": issue.description,
                "status": issue.status,
                "created_at": (
                    issue.created_at.isoformat()
                    if issue.created_at
                    else None
                ),
            }
            for issue in issues
        ],
    }

def create_maintenance_request(user, title, description):
    """
    Create a maintenance request for the authenticated tenant.
    """

    tenant = Tenant.query.filter_by(
        user_id=user.id
    ).first()

    if not tenant:
        return {
            "success": False,
            "message": "No tenant profile is associated with this account."
        }

    title = (title or "").strip()
    description = (description or "").strip()

    if not title:
        return {
            "success": False,
            "message": "A maintenance request title is required."
        }

    if not description:
        return {
            "success": False,
            "message": "A maintenance request description is required."
        }

    if len(title) > 120:
        title = title[:120]

    issue = Issue(
        title=title,
        description=description,
        status="open",
        tenant_id=user.id,
        landlord_id=tenant.landlord_id,
    )

    db.session.add(issue)
    db.session.commit()

    return {
        "success": True,
        "message": "Maintenance request created successfully.",
        "request": {
            "id": issue.id,
            "title": issue.title,
            "description": issue.description,
            "status": issue.status,
            "created_at": (
                issue.created_at.isoformat()
                if issue.created_at
                else None
            ),
        },
    }

