"""
Payment Service Layer

Handles all payment-related business logic including:
- Creating and updating payments
- Recording payments (offline/online)
- Managing payment history and overdue payments
- Payment validation
- Invoice management
"""

from flask import current_app
from app.extensions import db
from app.models import Payment, Invoice, Tenant, Property, Unit
from datetime import datetime, timedelta
from sqlalchemy import func
import uuid
import logging

logger = logging.getLogger(__name__)


class PaymentService:
    """Service for handling payment operations."""

    @staticmethod
    def create_payment(tenant_id, amount, payment_method, payment_date=None,
                      status='pending', transaction_id=None, description=None,
                      is_offline=False, offline_reference=None, paybill_number=None,
                      fees=None, invoice_id=None):
        """
        Create a new payment record.

        Args:
            tenant_id: ID of the tenant making payment
            amount: Payment amount
            payment_method: Method of payment (mpesa, cash, etc)
            payment_date: Date of payment (defaults to today)
            status: Payment status (pending, confirmed, completed)
            transaction_id: M-Pesa transaction ID or reference
            description: Optional payment description
            is_offline: Whether this is an offline payment
            offline_reference: Reference for offline payment
            paybill_number: M-Pesa paybill number
            fees: Transaction fees
            invoice_id: Associated invoice ID

        Returns:
            Payment: Created payment object
        """
        try:
            # Get pending invoice if not provided
            if not invoice_id:
                invoice = Invoice.query.filter_by(
                    tenant_id=tenant_id,
                    status='pending'
                ).first()
                invoice_id = invoice.id if invoice else None

            payment = Payment(
                amount=amount,
                tenant_id=tenant_id,
                payment_method=payment_method,
                transaction_id=transaction_id or str(uuid.uuid4()),
                payment_date=payment_date or datetime.utcnow().date(),
                status=status,
                description=description,
                is_offline=is_offline,
                offline_reference=offline_reference,
                paybill_number=paybill_number,
                fees=fees,
                invoice_id=invoice_id
            )

            db.session.add(payment)
            db.session.flush()  # Flush to get payment ID

            # Update invoice if available
            if invoice_id:
                invoice = Invoice.query.get(invoice_id)
                if invoice:
                    invoice.amount_due = max(0, invoice.amount_due - amount)
                    invoice.status = 'paid' if invoice.amount_due <= 0 else 'partially_paid'

            db.session.commit()
            logger.info(f"Payment created: {payment.id} for tenant {tenant_id}")
            return payment

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating payment: {str(e)}")
            raise

    @staticmethod
    def record_payment_offline(tenant_id, amount, payment_date=None,
                              payment_method='cash', description=None,
                              offline_reference=None):
        """
        Record an offline payment (cash, check, etc).

        Args:
            tenant_id: ID of paying tenant
            amount: Payment amount
            payment_date: Date of payment
            payment_method: Method (cash, check, etc)
            description: Optional description
            offline_reference: Reference number

        Returns:
            Payment: Created offline payment
        """
        return PaymentService.create_payment(
            tenant_id=tenant_id,
            amount=amount,
            payment_method=payment_method,
            payment_date=payment_date or datetime.utcnow().date(),
            status='confirmed',
            is_offline=True,
            offline_reference=offline_reference,
            description=description
        )

    @staticmethod
    def initiate_mpesa_payment(tenant_id, amount, phone_number, account_reference=None):
        """
        Initiate M-Pesa STK push payment.

        Args:
            tenant_id: ID of tenant
            amount: Payment amount
            phone_number: Tenant's phone number
            account_reference: Account reference for M-Pesa

        Returns:
            dict: {success: bool, checkout_id: str or None, message: str}
        """
        try:
            mpesa = current_app.mpesa_api

            # Ensure token is valid or refresh
            if not mpesa.is_token_valid():
                if not mpesa.refresh_token():
                    return {
                        'success': False,
                        'checkout_id': None,
                        'message': 'Failed to authenticate with M-Pesa'
                    }

            account_reference = account_reference or f"Tenant-{tenant_id}"
            
            checkout_id = mpesa.initiate_stk_push(
                phone_number=phone_number,
                amount=amount,
                account_reference=account_reference,
                transaction_description='Monthly Rent'
            )

            if checkout_id:
                logger.info(f"M-Pesa payment initiated for tenant {tenant_id}: {checkout_id}")
                return {
                    'success': True,
                    'checkout_id': checkout_id,
                    'message': 'Payment initiated. Confirm on your phone.'
                }
            else:
                return {
                    'success': False,
                    'checkout_id': None,
                    'message': 'Payment initiation failed'
                }

        except Exception as e:
            logger.error(f"Error initiating M-Pesa payment: {str(e)}")
            return {
                'success': False,
                'checkout_id': None,
                'message': str(e)
            }

    @staticmethod
    def get_payment_history(landlord_id, limit=None):
        """
        Get payment history for a landlord's properties.

        Args:
            landlord_id: ID of landlord
            limit: Maximum number of payments to return

        Returns:
            list: List of payments with tenant info
        """
        try:
            landlord_properties = Property.query.filter_by(landlord_id=landlord_id).all()
            property_ids = [p.id for p in landlord_properties]

            tenants = Tenant.query.filter(
                Tenant.property_id.in_(property_ids)
            ).all()
            tenant_ids = [t.id for t in tenants]

            query = Payment.query.filter(
                Payment.tenant_id.in_(tenant_ids)
            ).order_by(Payment.payment_date.desc())

            if limit:
                query = query.limit(limit)

            payments = query.all()

            # Enrich with tenant info
            result = []
            for payment in payments:
                tenant = Tenant.query.get(payment.tenant_id)
                payment.tenant_name = f"{tenant.first_name} {tenant.last_name}" if tenant else "Unknown"
                payment.property_name = tenant.property.name if tenant and tenant.property else "N/A"
                result.append(payment)

            return result

        except Exception as e:
            logger.error(f"Error fetching payment history: {str(e)}")
            raise

    @staticmethod
    def get_overdue_payments(landlord_id):
        """
        Get list of overdue payments for landlord's tenants.

        Args:
            landlord_id: ID of landlord

        Returns:
            list: List of overdue payment info
        """
        try:
            landlord_properties = Property.query.filter_by(landlord_id=landlord_id).all()
            property_ids = [p.id for p in landlord_properties]
            tenant_ids = [
                t.id for t in Tenant.query.filter(
                    Tenant.property_id.in_(property_ids)
                ).all()
            ]

            today = datetime.utcnow().date()
            current_month_start = today.replace(day=1)
            next_month_start = (
                datetime(
                    today.year + (today.month == 12),
                    (today.month % 12) + 1,
                    1
                )
            ).date()

            overdue_tenants = []

            for tenant in Tenant.query.filter(
                Tenant.id.in_(tenant_ids),
                Tenant.status == 'active'
            ).all():
                due_day = tenant.due_day_of_month or 1

                try:
                    due_date = current_month_start.replace(day=due_day)
                except ValueError:
                    due_date = (next_month_start - timedelta(days=1))

                effective_due_date = due_date + timedelta(
                    days=tenant.grace_period_days or 0
                )

                if today > effective_due_date:
                    # Check if payment exists for current month
                    payment = Payment.query.filter(
                        Payment.tenant_id == tenant.id,
                        Payment.payment_date >= current_month_start,
                        Payment.payment_date < next_month_start,
                        Payment.status == 'confirmed'
                    ).first()

                    if not payment:
                        overdue_tenants.append({
                            'tenant_name': f"{tenant.first_name} {tenant.last_name}",
                            'property_name': tenant.property.name if tenant.property else "N/A",
                            'due_date': due_date,
                            'amount_due': tenant.rent_amount,
                            'days_overdue': (today - effective_due_date).days,
                            'tenant_id': tenant.id
                        })

            return overdue_tenants

        except Exception as e:
            logger.error(f"Error fetching overdue payments: {str(e)}")
            raise

    @staticmethod
    def get_payment_metrics(landlord_id):
        """
        Calculate payment metrics for landlord dashboard.

        Args:
            landlord_id: ID of landlord

        Returns:
            dict: Payment metrics including totals, rates, etc
        """
        try:
            today = datetime.utcnow().date()
            current_month_start = today.replace(day=1)
            next_month_start = (
                datetime(
                    today.year + (today.month == 12),
                    (today.month % 12) + 1,
                    1
                )
            ).date()

            landlord_properties = Property.query.filter_by(landlord_id=landlord_id).all()
            property_ids = [p.id for p in landlord_properties]

            landlord_tenant_ids = [
                t.id for t in Tenant.query.filter(
                    Tenant.property_id.in_(property_ids)
                ).all()
            ]

            # Total collected this month
            total_collected = Payment.query.filter(
                Payment.tenant_id.in_(landlord_tenant_ids),
                Payment.payment_date >= current_month_start,
                Payment.payment_date < next_month_start,
                Payment.status == 'confirmed'
            ).with_entities(func.sum(Payment.amount)).scalar() or 0.00

            # Collection rate
            active_tenants = Tenant.query.filter(
                Tenant.property_id.in_(property_ids),
                Tenant.status == 'active'
            ).count()

            tenants_paid = Payment.query.filter(
                Payment.tenant_id.in_(landlord_tenant_ids),
                Payment.payment_date >= current_month_start,
                Payment.payment_date < next_month_start,
                Payment.status == 'confirmed'
            ).with_entities(func.count(func.distinct(Payment.tenant_id))).scalar() or 0

            collection_rate = (
                (tenants_paid / active_tenants * 100) if active_tenants > 0 else 0
            )

            # Recent transactions (last 7 days)
            seven_days_ago = today - timedelta(days=7)
            recent_transactions = Payment.query.filter(
                Payment.tenant_id.in_(landlord_tenant_ids),
                Payment.status == 'confirmed',
                Payment.payment_date >= seven_days_ago
            ).count()

            return {
                'total_collected': round(total_collected, 2),
                'collection_rate': round(collection_rate, 2),
                'recent_transactions': recent_transactions,
                'active_tenants': active_tenants,
                'tenants_paid': tenants_paid
            }

        except Exception as e:
            logger.error(f"Error calculating payment metrics: {str(e)}")
            raise

    @staticmethod
    def check_duplicate_transaction(transaction_id):
        """
        Check if transaction ID already exists.

        Args:
            transaction_id: Transaction ID to check

        Returns:
            Payment: Existing payment or None
        """
        return Payment.query.filter_by(transaction_id=transaction_id).first()

    @staticmethod
    def get_recent_payments(landlord_id, limit=5):
        """
        Get recent payments for dashboard.

        Args:
            landlord_id: ID of landlord
            limit: Number of recent payments to return

        Returns:
            list: Recent payments with formatted data
        """
        try:
            landlord_properties = Property.query.filter_by(landlord_id=landlord_id).all()
            property_ids = [p.id for p in landlord_properties]

            landlord_tenant_ids = [
                t.id for t in Tenant.query.filter(
                    Tenant.property_id.in_(property_ids)
                ).all()
            ]

            recent_payments_query = Payment.query.filter(
                Payment.tenant_id.in_(landlord_tenant_ids),
                Payment.status == 'confirmed'
            ).join(Tenant).order_by(Payment.payment_date.desc()).limit(limit).all()

            result = []
            for payment in recent_payments_query:
                if isinstance(payment.payment_date, str):
                    payment.payment_date = datetime.strptime(
                        payment.payment_date,
                        "%Y-%m-%d"
                    )

                tenant = payment.tenant
                if not tenant:
                    continue

                result.append({
                    'tenant_name': f"{tenant.first_name} {tenant.last_name}",
                    'property_name': tenant.property.name if tenant.property else 'N/A',
                    'amount': payment.amount,
                    'payment_date': payment.payment_date,
                    'formatted_date': payment.payment_date.strftime("%d/%m/%Y"),
                    'status': payment.status
                })

            return result

        except Exception as e:
            logger.error(f"Error fetching recent payments: {str(e)}")
            raise

    @staticmethod
    def update_payment_status(payment_id, new_status):
        """
        Update payment status (useful for M-Pesa callbacks).

        Args:
            payment_id: ID of payment
            new_status: New status value

        Returns:
            Payment: Updated payment or None
        """
        try:
            payment = Payment.query.get(payment_id)
            if payment:
                payment.status = new_status
                db.session.commit()
                logger.info(f"Payment {payment_id} status updated to {new_status}")
            return payment
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating payment status: {str(e)}")
            raise
