"""
Property Service Layer

Handles all property-related business logic including:
- Creating and updating properties
- Property management
- Unit management
- Property validation
"""

from flask import current_app
from app.extensions import db
from app.models import Property, Unit, Tenant
import logging

logger = logging.getLogger(__name__)


class PropertyService:
    """Service for handling property operations."""

    @staticmethod
    def create_property(landlord_id, name, address, property_type,
                       county_name, number_of_units, unit_numbers,
                       description=None, amenities=None):
        """
        Create a new property.

        Args:
            landlord_id: ID of landlord/owner
            name: Property name
            address: Property address
            property_type: Type (apartment, house, commercial, etc)
            county_name: County/district name
            number_of_units: Number of units
            unit_numbers: List of unit numbers/identifiers
            description: Optional description
            amenities: Optional amenities list

        Returns:
            Property: Created property object
        """
        try:
            property_obj = Property(
                landlord_id=landlord_id,
                name=name,
                address=address,
                property_type=property_type,
                county_name=county_name,
                number_of_units=number_of_units,
                unit_numbers=','.join(unit_numbers) if isinstance(unit_numbers, list) else unit_numbers,
                description=description,
                amenities=amenities
            )

            db.session.add(property_obj)
            db.session.flush()

            # Create units for the property
            if isinstance(unit_numbers, str):
                unit_numbers = [u.strip() for u in unit_numbers.split(',')]

            for unit_number in unit_numbers:
                unit = Unit(
                    property_id=property_obj.id,
                    unit_number=unit_number,
                    status='vacant'
                )
                db.session.add(unit)

            db.session.commit()
            logger.info(f"Property created: {property_obj.id} - {name}")
            return property_obj

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating property: {str(e)}")
            raise

    @staticmethod
    def update_property(property_id, **kwargs):
        """
        Update property information.

        Args:
            property_id: ID of property
            **kwargs: Fields to update

        Returns:
            Property: Updated property object
        """
        try:
            property_obj = Property.query.get(property_id)
            if not property_obj:
                raise ValueError(f"Property {property_id} not found")

            for key, value in kwargs.items():
                if key == 'unit_numbers' and isinstance(value, list):
                    value = ','.join(value)

                if hasattr(property_obj, key):
                    setattr(property_obj, key, value)

            db.session.commit()
            logger.info(f"Property updated: {property_id}")
            return property_obj

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating property: {str(e)}")
            raise

    @staticmethod
    def get_property_by_id(property_id):
        """
        Get property by ID.

        Args:
            property_id: ID of property

        Returns:
            Property: Property object or None
        """
        return Property.query.get(property_id)

    @staticmethod
    def get_landlord_properties(landlord_id):
        """
        Get all properties for a landlord.

        Args:
            landlord_id: ID of landlord

        Returns:
            list: List of properties
        """
        return Property.query.filter_by(landlord_id=landlord_id).all()

    @staticmethod
    def delete_property(property_id):
        """
        Delete a property and associated units and tenants.

        Args:
            property_id: ID of property

        Returns:
            bool: True if successful
        """
        try:
            property_obj = Property.query.get(property_id)
            if not property_obj:
                raise ValueError(f"Property {property_id} not found")

            # This will cascade delete units and handle tenant relationships
            db.session.delete(property_obj)
            db.session.commit()
            logger.info(f"Property deleted: {property_id}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting property: {str(e)}")
            raise

    @staticmethod
    def get_property_units(property_id):
        """
        Get all units in a property.

        Args:
            property_id: ID of property

        Returns:
            list: List of units
        """
        return Unit.query.filter_by(property_id=property_id).all()

    @staticmethod
    def get_vacant_units(property_id):
        """
        Get vacant units in a property.

        Args:
            property_id: ID of property

        Returns:
            list: Vacant units
        """
        return Unit.query.filter_by(
            property_id=property_id,
            status='vacant'
        ).all()

    @staticmethod
    def get_occupied_units(property_id):
        """
        Get occupied units in a property.

        Args:
            property_id: ID of property

        Returns:
            list: Occupied units
        """
        return Unit.query.filter_by(
            property_id=property_id,
            status='occupied'
        ).all()

    @staticmethod
    def get_property_statistics(property_id):
        """
        Get statistics for a property.

        Args:
            property_id: ID of property

        Returns:
            dict: Property statistics
        """
        try:
            units = Unit.query.filter_by(property_id=property_id).all()
            total_units = len(units)

            vacant_units = len([u for u in units if u.status == 'vacant'])
            occupied_units = len([u for u in units if u.status == 'occupied'])
            maintenance_units = len([u for u in units if u.status == 'maintenance'])

            occupancy_rate = (
                (occupied_units / total_units * 100) if total_units > 0 else 0
            )

            # Get total expected monthly rent
            tenants = Tenant.query.filter_by(property_id=property_id).all()
            total_expected_rent = sum(t.rent_amount for t in tenants if t.status == 'active')

            return {
                'total_units': total_units,
                'occupied_units': occupied_units,
                'vacant_units': vacant_units,
                'maintenance_units': maintenance_units,
                'occupancy_rate': round(occupancy_rate, 2),
                'vacancy_rate': round(100 - occupancy_rate, 2),
                'total_expected_rent': round(total_expected_rent, 2),
                'active_tenants': len([t for t in tenants if t.status == 'active'])
            }

        except Exception as e:
            logger.error(f"Error getting property statistics: {str(e)}")
            raise

    @staticmethod
    def add_unit_to_property(property_id, unit_number):
        """
        Add a new unit to a property.

        Args:
            property_id: ID of property
            unit_number: Unit identifier

        Returns:
            Unit: Created unit
        """
        try:
            # Check if unit already exists
            existing = Unit.query.filter_by(
                property_id=property_id,
                unit_number=unit_number
            ).first()

            if existing:
                raise ValueError(f"Unit {unit_number} already exists in this property")

            unit = Unit(
                property_id=property_id,
                unit_number=unit_number,
                status='vacant'
            )

            db.session.add(unit)
            db.session.commit()
            logger.info(f"Unit {unit_number} added to property {property_id}")
            return unit

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding unit: {str(e)}")
            raise

    @staticmethod
    def remove_unit_from_property(unit_id):
        """
        Remove a unit from a property.

        Args:
            unit_id: ID of unit

        Returns:
            bool: True if successful
        """
        try:
            unit = Unit.query.get(unit_id)
            if not unit:
                raise ValueError(f"Unit {unit_id} not found")

            # Check if unit has active tenant
            tenant = Tenant.query.filter_by(unit_id=unit_id).first()
            if tenant and tenant.status == 'active':
                raise ValueError("Cannot remove unit with active tenant")

            db.session.delete(unit)
            db.session.commit()
            logger.info(f"Unit deleted: {unit_id}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error removing unit: {str(e)}")
            raise

    @staticmethod
    def update_unit_status(unit_id, new_status):
        """
        Update unit status.

        Args:
            unit_id: ID of unit
            new_status: New status (vacant, occupied, maintenance)

        Returns:
            Unit: Updated unit
        """
        try:
            unit = Unit.query.get(unit_id)
            if not unit:
                raise ValueError(f"Unit {unit_id} not found")

            unit.status = new_status
            db.session.commit()
            logger.info(f"Unit {unit_id} status updated to {new_status}")
            return unit

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating unit status: {str(e)}")
            raise

    @staticmethod
    def get_property_overview(landlord_id):
        """
        Get overview of all landlord's properties.

        Args:
            landlord_id: ID of landlord

        Returns:
            list: Properties with statistics
        """
        try:
            properties = Property.query.filter_by(landlord_id=landlord_id).all()

            overview = []
            for prop in properties:
                stats = PropertyService.get_property_statistics(prop.id)
                overview.append({
                    'id': prop.id,
                    'name': prop.name,
                    'address': prop.address,
                    'property_type': prop.property_type,
                    'county': prop.county_name,
                    **stats
                })

            return overview

        except Exception as e:
            logger.error(f"Error getting property overview: {str(e)}")
            raise
