"""
Report Service Layer

Handles all report-related business logic including:
- Financial reports
- Payment reports
- Occupancy reports
- Tenant reports
- Report generation and export
"""

from flask import current_app
from app.extensions import db
from app.models import Payment, Tenant, Property, Unit, Invoice
from datetime import datetime, timedelta
from sqlalchemy import func
import csv
import io
import logging

logger = logging.getLogger(__name__)


class ReportService:
    """Service for generating reports and analytics."""

    @staticmethod
    def get_financial_report(landlord_id, start_date=None, end_date=None):
        """
        Generate financial report for landlord.

        Args:
            landlord_id: ID of landlord
            start_date: Report start date
            end_date: Report end date

        Returns:
            dict: Financial report data
        """
        try:
            if not end_date:
                end_date = datetime.utcnow().date()
            if not start_date:
                start_date = end_date.replace(day=1)

            landlord_properties = Property.query.filter_by(landlord_id=landlord_id).all()
            property_ids = [p.id for p in landlord_properties]

            landlord_tenant_ids = [
                t.id for t in Tenant.query.filter(
                    Tenant.property_id.in_(property_ids)
                ).all()
            ]

            # Total income
            total_income = Payment.query.filter(
                Payment.tenant_id.in_(landlord_tenant_ids),
                Payment.payment_date >= start_date,
                Payment.payment_date <= end_date,
                Payment.status == 'confirmed'
            ).with_entities(func.sum(Payment.amount)).scalar() or 0.00

            # Total due
            total_due = Tenant.query.filter(
                Tenant.property_id.in_(property_ids),
                Tenant.status == 'active'
            ).with_entities(func.sum(Tenant.rent_amount)).scalar() or 0.00

            # Payment count
            payment_count = Payment.query.filter(
                Payment.tenant_id.in_(landlord_tenant_ids),
                Payment.payment_date >= start_date,
                Payment.payment_date <= end_date,
                Payment.status == 'confirmed'
            ).count()

            return {
                'period': f"{start_date} to {end_date}",
                'total_income': round(total_income, 2),
                'total_due': round(total_due, 2),
                'collection_rate': round((total_income / total_due * 100) if total_due > 0 else 0, 2),
                'payment_count': payment_count,
                'num_properties': len(landlord_properties),
                'num_tenants': len(landlord_tenant_ids)
            }

        except Exception as e:
            logger.error(f"Error generating financial report: {str(e)}")
            raise

    @staticmethod
    def get_occupancy_report(landlord_id):
        """
        Generate occupancy report for landlord's properties.

        Args:
            landlord_id: ID of landlord

        Returns:
            dict: Occupancy data
        """
        try:
            landlord_properties = Property.query.filter_by(landlord_id=landlord_id).all()
            property_ids = [p.id for p in landlord_properties]

            # Total units
            total_units = Unit.query.filter(
                Unit.property_id.in_(property_ids)
            ).count()

            # Occupied units
            occupied_units = Tenant.query.filter(
                Tenant.property_id.in_(property_ids),
                Tenant.status == 'active',
                Tenant.unit_id.isnot(None)
            ).count()

            # Vacant units
            vacant_units = Unit.query.filter(
                Unit.property_id.in_(property_ids),
                Unit.status == 'vacant'
            ).count()

            # Units under maintenance
            maintenance_units = Unit.query.filter(
                Unit.property_id.in_(property_ids),
                Unit.status == 'maintenance'
            ).count()

            occupancy_rate = (
                (occupied_units / total_units * 100) if total_units > 0 else 0
            )

            return {
                'total_units': total_units,
                'occupied_units': occupied_units,
                'vacant_units': vacant_units,
                'maintenance_units': maintenance_units,
                'occupancy_rate': round(occupancy_rate, 2),
                'vacancy_rate': round(100 - occupancy_rate, 2)
            }

        except Exception as e:
            logger.error(f"Error generating occupancy report: {str(e)}")
            raise

    @staticmethod
    def get_tenant_report(landlord_id):
        """
        Generate detailed tenant report.

        Args:
            landlord_id: ID of landlord

        Returns:
            list: Tenant information
        """
        try:
            landlord_properties = Property.query.filter_by(landlord_id=landlord_id).all()
            property_ids = [p.id for p in landlord_properties]

            tenants = Tenant.query.filter(
                Tenant.property_id.in_(property_ids)
            ).all()

            tenant_data = []
            for tenant in tenants:
                # Get latest payment
                latest_payment = Payment.query.filter_by(
                    tenant_id=tenant.id,
                    status='confirmed'
                ).order_by(Payment.payment_date.desc()).first()

                # Calculate if overdue
                today = datetime.utcnow().date()
                current_month_start = today.replace(day=1)
                due_date = current_month_start.replace(day=tenant.due_day_of_month or 1)
                effective_due_date = due_date + timedelta(days=tenant.grace_period_days or 0)

                is_overdue = today > effective_due_date
                payment_exists = Payment.query.filter(
                    Payment.tenant_id == tenant.id,
                    Payment.payment_date >= current_month_start,
                    Payment.status == 'confirmed'
                ).first()

                tenant_data.append({
                    'tenant_id': tenant.id,
                    'name': f"{tenant.first_name} {tenant.last_name}",
                    'email': tenant.email,
                    'phone': tenant.phone_number,
                    'property': tenant.property.name if tenant.property else 'N/A',
                    'rent_amount': tenant.rent_amount,
                    'status': tenant.status,
                    'lease_start': tenant.lease_start_date,
                    'lease_end': tenant.lease_end_date,
                    'last_payment_date': latest_payment.payment_date if latest_payment else None,
                    'last_payment_amount': latest_payment.amount if latest_payment else None,
                    'is_overdue': is_overdue and not payment_exists,
                    'payment_status': 'Paid' if payment_exists else 'Pending'
                })

            return tenant_data

        except Exception as e:
            logger.error(f"Error generating tenant report: {str(e)}")
            raise

    @staticmethod
    def get_payment_report(landlord_id, start_date=None, end_date=None):
        """
        Generate detailed payment report.

        Args:
            landlord_id: ID of landlord
            start_date: Report start date
            end_date: Report end date

        Returns:
            list: Payment details
        """
        try:
            if not end_date:
                end_date = datetime.utcnow().date()
            if not start_date:
                start_date = end_date.replace(day=1)

            landlord_properties = Property.query.filter_by(landlord_id=landlord_id).all()
            property_ids = [p.id for p in landlord_properties]

            landlord_tenant_ids = [
                t.id for t in Tenant.query.filter(
                    Tenant.property_id.in_(property_ids)
                ).all()
            ]

            payments = Payment.query.filter(
                Payment.tenant_id.in_(landlord_tenant_ids),
                Payment.payment_date >= start_date,
                Payment.payment_date <= end_date
            ).order_by(Payment.payment_date.desc()).all()

            payment_data = []
            for payment in payments:
                tenant = Tenant.query.get(payment.tenant_id)
                payment_data.append({
                    'payment_id': payment.id,
                    'tenant_name': f"{tenant.first_name} {tenant.last_name}" if tenant else 'Unknown',
                    'property': tenant.property.name if tenant and tenant.property else 'N/A',
                    'amount': payment.amount,
                    'payment_date': payment.payment_date,
                    'payment_method': payment.payment_method,
                    'transaction_id': payment.transaction_id,
                    'status': payment.status,
                    'is_offline': payment.is_offline
                })

            return payment_data

        except Exception as e:
            logger.error(f"Error generating payment report: {str(e)}")
            raise

    @staticmethod
    def export_financial_report_csv(landlord_id, start_date=None, end_date=None):
        """
        Export financial report as CSV.

        Args:
            landlord_id: ID of landlord
            start_date: Report start date
            end_date: Report end date

        Returns:
            str: CSV content
        """
        try:
            report = ReportService.get_financial_report(landlord_id, start_date, end_date)
            payments = ReportService.get_payment_report(landlord_id, start_date, end_date)

            output = io.StringIO()
            writer = csv.writer(output)

            # Header
            writer.writerow(['MFUKO7 - Financial Report'])
            writer.writerow([f"Period: {report['period']}"])
            writer.writerow([''])

            # Summary
            writer.writerow(['Summary'])
            writer.writerow(['Total Income', f"KES {report['total_income']:,.2f}"])
            writer.writerow(['Total Due', f"KES {report['total_due']:,.2f}"])
            writer.writerow(['Collection Rate', f"{report['collection_rate']}%"])
            writer.writerow(['Payment Count', report['payment_count']])
            writer.writerow([''])

            # Payment details
            writer.writerow(['Payment Details'])
            writer.writerow([
                'Date', 'Tenant', 'Property', 'Amount', 'Method', 'Status'
            ])

            for payment in payments:
                writer.writerow([
                    payment['payment_date'],
                    payment['tenant_name'],
                    payment['property'],
                    f"KES {payment['amount']:,.2f}",
                    payment['payment_method'],
                    payment['status']
                ])

            return output.getvalue()

        except Exception as e:
            logger.error(f"Error exporting financial report: {str(e)}")
            raise

    @staticmethod
    def export_tenant_report_csv(landlord_id):
        """
        Export tenant report as CSV.

        Args:
            landlord_id: ID of landlord

        Returns:
            str: CSV content
        """
        try:
            tenants = ReportService.get_tenant_report(landlord_id)

            output = io.StringIO()
            writer = csv.writer(output)

            # Header
            writer.writerow(['MFUKO7 - Tenant Report'])
            writer.writerow([f"Generated: {datetime.utcnow().date()}"])
            writer.writerow([''])

            # Tenant details
            writer.writerow([
                'Tenant Name', 'Email', 'Phone', 'Property',
                'Rent Amount', 'Status', 'Lease Start', 'Lease End',
                'Last Payment', 'Payment Status'
            ])

            for tenant in tenants:
                writer.writerow([
                    tenant['name'],
                    tenant['email'],
                    tenant['phone'],
                    tenant['property'],
                    f"KES {tenant['rent_amount']:,.2f}",
                    tenant['status'],
                    tenant['lease_start'],
                    tenant['lease_end'],
                    tenant['last_payment_date'],
                    tenant['payment_status']
                ])

            return output.getvalue()

        except Exception as e:
            logger.error(f"Error exporting tenant report: {str(e)}")
            raise

    @staticmethod
    def get_monthly_revenue_trend(landlord_id, num_months=12):
        """
        Get monthly revenue trend for landlord.

        Args:
            landlord_id: ID of landlord
            num_months: Number of months to include

        Returns:
            list: Monthly revenue data
        """
        try:
            landlord_properties = Property.query.filter_by(landlord_id=landlord_id).all()
            property_ids = [p.id for p in landlord_properties]

            landlord_tenant_ids = [
                t.id for t in Tenant.query.filter(
                    Tenant.property_id.in_(property_ids)
                ).all()
            ]

            today = datetime.utcnow().date()
            trend = []

            for i in range(num_months):
                month_date = today - timedelta(days=30 * i)
                month_start = month_date.replace(day=1)

                # Calculate next month start
                if month_date.month == 12:
                    month_end = datetime(month_date.year + 1, 1, 1).date() - timedelta(days=1)
                else:
                    month_end = datetime(month_date.year, month_date.month + 1, 1).date() - timedelta(days=1)

                revenue = Payment.query.filter(
                    Payment.tenant_id.in_(landlord_tenant_ids),
                    Payment.payment_date >= month_start,
                    Payment.payment_date <= month_end,
                    Payment.status == 'confirmed'
                ).with_entities(func.sum(Payment.amount)).scalar() or 0.00

                trend.insert(0, {
                    'month': month_start.strftime("%Y-%m"),
                    'revenue': round(revenue, 2)
                })

            return trend

        except Exception as e:
            logger.error(f"Error getting monthly revenue trend: {str(e)}")
            raise

    @staticmethod
    def get_payment_method_distribution(landlord_id, start_date=None, end_date=None):
        """
        Get payment method distribution for landlord.

        Args:
            landlord_id: ID of landlord
            start_date: Report start date
            end_date: Report end date

        Returns:
            dict: Payment method breakdown
        """
        try:
            if not end_date:
                end_date = datetime.utcnow().date()
            if not start_date:
                start_date = end_date.replace(day=1)

            landlord_properties = Property.query.filter_by(landlord_id=landlord_id).all()
            property_ids = [p.id for p in landlord_properties]

            landlord_tenant_ids = [
                t.id for t in Tenant.query.filter(
                    Tenant.property_id.in_(property_ids)
                ).all()
            ]

            # Group by payment method
            methods = db.session.query(
                Payment.payment_method,
                func.count(Payment.id).label('count'),
                func.sum(Payment.amount).label('total')
            ).filter(
                Payment.tenant_id.in_(landlord_tenant_ids),
                Payment.payment_date >= start_date,
                Payment.payment_date <= end_date,
                Payment.status == 'confirmed'
            ).group_by(Payment.payment_method).all()

            result = {}
            for method, count, total in methods:
                result[method or 'Unknown'] = {
                    'count': count,
                    'total': round(total or 0, 2),
                    'percentage': 0  # Will calculate below
                }

            # Calculate percentages
            total_amount = sum(v['total'] for v in result.values())
            for method in result:
                if total_amount > 0:
                    result[method]['percentage'] = round(
                        (result[method]['total'] / total_amount * 100), 2
                    )

            return result

        except Exception as e:
            logger.error(f"Error getting payment method distribution: {str(e)}")
            raise
