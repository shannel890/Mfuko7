"""
Tenant Service Layer

Handles all tenant-related business logic including:
- Creating and updating tenants
- Tenant validation
- Tenant queries and filtering
- Lease management
- Tenant status management
"""

from flask import current_app
from app.extensions import db
from app.models import Tenant, Property, Unit, User, Payment, Invoice
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class TenantService:
    """Service for handling tenant operations."""

    @staticmethod
    def create_tenant(first_name, last_name, email, phone_number, property_id,
                     rent_amount, due_day_of_month=1, grace_period_days=5,
                     lease_start_date=None, lease_end_date=None, national_id=None,
                     status='active', user_id=None):
        """
        Create a new tenant.

        Args:
            first_name: Tenant's first name
            last_name: Tenant's last name
            email: Tenant's email
            phone_number: Tenant's phone number
            property_id: ID of property/landlord
            rent_amount: Monthly rent amount
            due_day_of_month: Day of month when rent is due
            grace_period_days: Grace period after due date
            lease_start_date: Start date of lease
            lease_end_date: End date of lease
            national_id: National ID number
            status: Tenant status (active, inactive, evicted)
            user_id: Associated user ID (for tenant account)

        Returns:
            Tenant: Created tenant object
        """
        try:
            tenant = Tenant(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone_number=phone_number,
                property_id=property_id,
                rent_amount=rent_amount,
                due_day_of_month=due_day_of_month,
                grace_period_days=grace_period_days,
                lease_start_date=lease_start_date,
                lease_end_date=lease_end_date,
                national_id=national_id,
                status=status,
                user_id=user_id
            )

            db.session.add(tenant)
            db.session.commit()
            logger.info(f"Tenant created: {tenant.id} - {first_name} {last_name}")
            return tenant

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating tenant: {str(e)}")
            raise

    @staticmethod
    def update_tenant(tenant_id, **kwargs):
        """
        Update tenant information.

        Args:
            tenant_id: ID of tenant
            **kwargs: Fields to update

        Returns:
            Tenant: Updated tenant object
        """
        try:
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")

            for key, value in kwargs.items():
                if hasattr(tenant, key):
                    setattr(tenant, key, value)

            db.session.commit()
            logger.info(f"Tenant updated: {tenant_id}")
            return tenant

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating tenant: {str(e)}")
            raise

    @staticmethod
    def get_tenant_by_id(tenant_id):
        """
        Get tenant by ID.

        Args:
            tenant_id: ID of tenant

        Returns:
            Tenant: Tenant object or None
        """
        return Tenant.query.get(tenant_id)

    @staticmethod
    def get_tenant_by_user_id(user_id):
        """
        Get tenant profile for a user.

        Args:
            user_id: ID of user

        Returns:
            Tenant: Tenant object or None
        """
        return Tenant.query.filter_by(user_id=user_id).first()

    @staticmethod
    def get_tenants_for_landlord(landlord_id):
        """
        Get all tenants for a landlord's properties.

        Args:
            landlord_id: ID of landlord/user

        Returns:
            list: List of tenants
        """
        try:
            landlord_properties = Property.query.filter_by(landlord_id=landlord_id).all()
            property_ids = [p.id for p in landlord_properties]
            tenants = Tenant.query.filter(Tenant.property_id.in_(property_ids)).all()
            return tenants

        except Exception as e:
            logger.error(f"Error fetching tenants for landlord: {str(e)}")
            raise

    @staticmethod
    def get_tenants_for_property(property_id):
        """
        Get all tenants for a specific property.

        Args:
            property_id: ID of property

        Returns:
            list: List of tenants in property
        """
        return Tenant.query.filter_by(property_id=property_id).all()

    @staticmethod
    def assign_tenant_to_unit(tenant_id, unit_id):
        """
        Assign tenant to a unit.

        Args:
            tenant_id: ID of tenant
            unit_id: ID of unit

        Returns:
            Tenant: Updated tenant object
        """
        try:
            tenant = Tenant.query.get(tenant_id)
            unit = Unit.query.get(unit_id)

            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")
            if not unit:
                raise ValueError(f"Unit {unit_id} not found")

            # Update tenant
            tenant.unit_id = unit_id
            tenant.property_id = unit.property_id

            # Update unit status
            unit.status = 'occupied'

            db.session.commit()
            logger.info(f"Tenant {tenant_id} assigned to unit {unit_id}")
            return tenant

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error assigning tenant to unit: {str(e)}")
            raise

    @staticmethod
    def unassign_tenant_from_unit(tenant_id):
        """
        Remove tenant from unit.

        Args:
            tenant_id: ID of tenant

        Returns:
            Tenant: Updated tenant object
        """
        try:
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")

            # Mark unit as vacant if assigned
            if tenant.unit_id:
                unit = Unit.query.get(tenant.unit_id)
                if unit:
                    unit.status = 'vacant'

            tenant.unit_id = None
            db.session.commit()
            logger.info(f"Tenant {tenant_id} unassigned from unit")
            return tenant

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error unassigning tenant from unit: {str(e)}")
            raise

    @staticmethod
    def delete_tenant(tenant_id):
        """
        Delete a tenant.

        Args:
            tenant_id: ID of tenant

        Returns:
            bool: True if successful
        """
        try:
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")

            # Unassign from unit first
            if tenant.unit_id:
                TenantService.unassign_tenant_from_unit(tenant_id)

            db.session.delete(tenant)
            db.session.commit()
            logger.info(f"Tenant deleted: {tenant_id}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting tenant: {str(e)}")
            raise

    @staticmethod
    def get_active_tenants(landlord_id):
        """
        Get all active tenants for a landlord.

        Args:
            landlord_id: ID of landlord

        Returns:
            list: Active tenants
        """
        try:
            landlord_properties = Property.query.filter_by(landlord_id=landlord_id).all()
            property_ids = [p.id for p in landlord_properties]

            tenants = Tenant.query.filter(
                Tenant.property_id.in_(property_ids),
                Tenant.status == 'active'
            ).all()

            return tenants

        except Exception as e:
            logger.error(f"Error fetching active tenants: {str(e)}")
            raise

    @staticmethod
    def get_tenant_rent_info(tenant_id):
        """
        Get tenant's rent and payment information.

        Args:
            tenant_id: ID of tenant

        Returns:
            dict: Rent info including amount, due date, payments
        """
        try:
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")

            today = datetime.utcnow().date()
            current_month_start = today.replace(day=1)
            due_day = tenant.due_day_of_month or 1

            try:
                due_date = current_month_start.replace(day=due_day)
            except ValueError:
                next_month = (datetime(today.year + (today.month == 12), (today.month % 12) + 1, 1)).date()
                due_date = next_month - timedelta(days=1)

            # Get pending invoice
            invoice = Invoice.query.filter_by(
                tenant_id=tenant_id,
                status='pending'
            ).first()

            amount_due = invoice.amount_due if invoice else tenant.rent_amount

            # Get latest payment
            latest_payment = Payment.query.filter_by(
                tenant_id=tenant_id,
                status='confirmed'
            ).order_by(Payment.payment_date.desc()).first()

            return {
                'rent_amount': tenant.rent_amount,
                'due_date': due_date,
                'due_day': due_day,
                'grace_period_days': tenant.grace_period_days,
                'amount_due': amount_due,
                'last_payment_date': latest_payment.payment_date if latest_payment else None,
                'last_payment_amount': latest_payment.amount if latest_payment else None,
                'is_overdue': today > (due_date + timedelta(days=tenant.grace_period_days or 0))
            }

        except Exception as e:
            logger.error(f"Error getting tenant rent info: {str(e)}")
            raise

    @staticmethod
    def create_or_get_tenant_profile(user_id, first_name, last_name, email):
        """
        Create or get tenant profile for a user.

        Args:
            user_id: ID of user
            first_name: First name
            last_name: Last name
            email: Email address

        Returns:
            Tenant: Tenant profile
        """
        try:
            # Check if tenant profile already exists
            tenant = Tenant.query.filter_by(user_id=user_id).first()

            if tenant:
                return tenant

            # Create new tenant profile
            tenant = Tenant(
                user_id=user_id,
                first_name=first_name,
                last_name=last_name,
                email=email,
                status='active',
                grace_period_days=5
            )

            db.session.add(tenant)
            db.session.commit()
            logger.info(f"Tenant profile created for user {user_id}")
            return tenant

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating tenant profile: {str(e)}")
            raise

    @staticmethod
    def get_available_properties_for_tenant():
        """
        Get available properties with vacant units.

        Returns:
            list: Properties with available units
        """
        try:
            vacant_units = Unit.query.filter_by(status='vacant').all()
            available_properties = {}

            for unit in vacant_units:
                property_obj = unit.property
                if not property_obj:
                    continue

                prop_id = property_obj.id
                if prop_id not in available_properties:
                    available_properties[prop_id] = {
                        'id': prop_id,
                        'name': property_obj.name,
                        'address': property_obj.address,
                        'property_type': property_obj.property_type,
                        'units_available': 0
                    }

                available_properties[prop_id]['units_available'] += 1

            return list(available_properties.values())

        except Exception as e:
            logger.error(f"Error getting available properties: {str(e)}")
            raise

    @staticmethod
    def extend_lease(tenant_id, new_end_date):
        """
        Extend tenant's lease.

        Args:
            tenant_id: ID of tenant
            new_end_date: New lease end date

        Returns:
            Tenant: Updated tenant
        """
        try:
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")

            tenant.lease_end_date = new_end_date
            db.session.commit()
            logger.info(f"Lease extended for tenant {tenant_id} until {new_end_date}")
            return tenant

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error extending lease: {str(e)}")
            raise

    @staticmethod
    def terminate_lease(tenant_id, termination_date=None):
        """
        Terminate tenant's lease.

        Args:
            tenant_id: ID of tenant
            termination_date: Date of termination

        Returns:
            Tenant: Updated tenant
        """
        try:
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")

            tenant.status = 'inactive'
            tenant.lease_end_date = termination_date or datetime.utcnow().date()

            # Mark unit as vacant
            if tenant.unit_id:
                unit = Unit.query.get(tenant.unit_id)
                if unit:
                    unit.status = 'vacant'

            db.session.commit()
            logger.info(f"Lease terminated for tenant {tenant_id}")
            return tenant

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error terminating lease: {str(e)}")
            raise
