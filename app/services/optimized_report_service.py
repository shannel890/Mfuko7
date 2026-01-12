"""
Optimized Report Service with Read/Write Separation

Handles all report-related business logic with performance optimizations:
- Read-only session usage for reports
- Eager loading to prevent N+1 queries
- Query result caching
- Optimized aggregation queries
- Batch operations for large datasets
"""

from flask import current_app
from app.extensions import db
from app.db_utils import get_database_manager, query_cache, optimizer, read_only
from app.models import Payment, Tenant, Property, Unit, Invoice
from datetime import datetime, timedelta
from sqlalchemy import func, and_, select
from sqlalchemy.orm import joinedload
import csv
import io
import logging

logger = logging.getLogger(__name__)


class OptimizedReportService:
    """Optimized service for generating reports and analytics with read/write separation."""
    
    # Cache keys for reports
    CACHE_PREFIX = "report:"
    FINANCIAL_CACHE_KEY = f"{CACHE_PREFIX}financial"
    OCCUPANCY_CACHE_KEY = f"{CACHE_PREFIX}occupancy"
    TENANT_CACHE_KEY = f"{CACHE_PREFIX}tenant"
    PAYMENT_CACHE_KEY = f"{CACHE_PREFIX}payment"

    @staticmethod
    def _get_landlord_properties(landlord_id, session=None):
        """
        Get all property IDs for landlord efficiently.
        
        Uses eager loading to fetch in single query.
        """
        if session is None:
            session = db.session
        
        query = session.query(Property.id).filter_by(landlord_id=landlord_id)
        return [p[0] for p in query.all()]
    
    @staticmethod
    def _get_landlord_tenants(property_ids, session=None):
        """
        Get all tenant IDs for landlord's properties efficiently.
        
        Batch query to prevent N+1.
        """
        if session is None:
            session = db.session
        
        if not property_ids:
            return []
        
        query = session.query(Tenant.id).filter(
            Tenant.property_id.in_(property_ids)
        )
        return [t[0] for t in query.all()]

    @staticmethod
    def get_financial_report(landlord_id, start_date=None, end_date=None, use_cache=True):
        """
        Generate optimized financial report using read-only session.
        
        Optimizations:
        - Read-only session for consistency
        - Single aggregation query instead of multiple
        - Query result caching for repeated calls
        - Efficient filtering
        
        Args:
            landlord_id: ID of landlord
            start_date: Report start date (default: first day of month)
            end_date: Report end date (default: today)
            use_cache: Whether to use cached results
        
        Returns:
            dict: Financial report data
        """
        try:
            # Check cache first
            cache_key = f"{OptimizedReportService.FINANCIAL_CACHE_KEY}:{landlord_id}:{start_date}:{end_date}"
            if use_cache:
                cached = query_cache.get(cache_key)
                if cached:
                    logger.info(f"Cache hit for financial report: {landlord_id}")
                    return cached
            
            if not end_date:
                end_date = datetime.utcnow().date()
            if not start_date:
                start_date = end_date.replace(day=1)
            
            # Get database manager for read-only session
            db_manager = get_database_manager()
            if db_manager:
                read_session = db_manager.get_read_session()
            else:
                read_session = db.session
            
            try:
                # Get property and tenant IDs efficiently
                landlord_properties = read_session.query(Property.id).filter_by(
                    landlord_id=landlord_id
                ).all()
                property_ids = [p[0] for p in landlord_properties]
                
                if not property_ids:
                    return {
                        'period': f"{start_date} to {end_date}",
                        'total_income': 0.0,
                        'total_due': 0.0,
                        'collection_rate': 0.0,
                        'payment_count': 0,
                        'num_properties': 0,
                        'num_tenants': 0
                    }
                
                # Get all tenant IDs in single query
                landlord_tenants = read_session.query(Tenant.id).filter(
                    Tenant.property_id.in_(property_ids)
                ).all()
                tenant_ids = [t[0] for t in landlord_tenants]
                
                # Single aggregation query for income
                income_result = read_session.query(
                    func.coalesce(func.sum(Payment.amount), 0.0)
                ).filter(
                    Payment.tenant_id.in_(tenant_ids) if tenant_ids else False,
                    Payment.payment_date >= start_date,
                    Payment.payment_date <= end_date,
                    Payment.status == 'confirmed'
                ).scalar()
                total_income = float(income_result) if income_result else 0.0
                
                # Single aggregation query for due
                due_result = read_session.query(
                    func.coalesce(func.sum(Tenant.rent_amount), 0.0)
                ).filter(
                    Tenant.property_id.in_(property_ids),
                    Tenant.status == 'active'
                ).scalar()
                total_due = float(due_result) if due_result else 0.0
                
                # Count payments
                payment_count = read_session.query(func.count(Payment.id)).filter(
                    Payment.tenant_id.in_(tenant_ids) if tenant_ids else False,
                    Payment.payment_date >= start_date,
                    Payment.payment_date <= end_date,
                    Payment.status == 'confirmed'
                ).scalar() or 0
                
                report = {
                    'period': f"{start_date} to {end_date}",
                    'total_income': round(total_income, 2),
                    'total_due': round(total_due, 2),
                    'collection_rate': round((total_income / total_due * 100) if total_due > 0 else 0, 2),
                    'payment_count': payment_count,
                    'num_properties': len(property_ids),
                    'num_tenants': len(tenant_ids)
                }
                
                # Cache result
                if use_cache:
                    query_cache.set(cache_key, report)
                
                return report
            
            finally:
                if db_manager:
                    db_manager.close_read_session(read_session)
        
        except Exception as e:
            logger.error(f"Error generating financial report: {str(e)}")
            raise

    @staticmethod
    def get_occupancy_report(landlord_id, use_cache=True):
        """
        Generate optimized occupancy report using read-only session.
        
        Optimizations:
        - Read-only session
        - Single batch query for all unit statuses
        - Query result caching
        
        Args:
            landlord_id: ID of landlord
            use_cache: Whether to use cached results
        
        Returns:
            dict: Occupancy data
        """
        try:
            # Check cache
            cache_key = f"{OptimizedReportService.OCCUPANCY_CACHE_KEY}:{landlord_id}"
            if use_cache:
                cached = query_cache.get(cache_key)
                if cached:
                    logger.info(f"Cache hit for occupancy report: {landlord_id}")
                    return cached
            
            db_manager = get_database_manager()
            if db_manager:
                read_session = db_manager.get_read_session()
            else:
                read_session = db.session
            
            try:
                # Get property IDs
                properties = read_session.query(Property.id).filter_by(
                    landlord_id=landlord_id
                ).all()
                property_ids = [p[0] for p in properties]
                
                if not property_ids:
                    return {
                        'total_units': 0,
                        'occupied_units': 0,
                        'vacant_units': 0,
                        'maintenance_units': 0,
                        'occupancy_rate': 0.0,
                        'vacancy_rate': 0.0
                    }
                
                # Total units in single query
                total_units = read_session.query(func.count(Unit.id)).filter(
                    Unit.property_id.in_(property_ids)
                ).scalar() or 0
                
                # Occupied units: active tenants with assigned units
                occupied_units = read_session.query(func.count(Tenant.id)).filter(
                    Tenant.property_id.in_(property_ids),
                    Tenant.status == 'active',
                    Tenant.unit_id.isnot(None)
                ).scalar() or 0
                
                # Vacant and maintenance units in single batched query
                unit_statuses = read_session.query(
                    Unit.status,
                    func.count(Unit.id)
                ).filter(
                    Unit.property_id.in_(property_ids)
                ).group_by(Unit.status).all()
                
                status_counts = {status: count for status, count in unit_statuses}
                vacant_units = status_counts.get('vacant', 0)
                maintenance_units = status_counts.get('maintenance', 0)
                
                occupancy_rate = (
                    (occupied_units / total_units * 100) if total_units > 0 else 0
                )
                
                report = {
                    'total_units': total_units,
                    'occupied_units': occupied_units,
                    'vacant_units': vacant_units,
                    'maintenance_units': maintenance_units,
                    'occupancy_rate': round(occupancy_rate, 2),
                    'vacancy_rate': round(100 - occupancy_rate, 2)
                }
                
                # Cache result
                if use_cache:
                    query_cache.set(cache_key, report)
                
                return report
            
            finally:
                if db_manager:
                    db_manager.close_read_session(read_session)
        
        except Exception as e:
            logger.error(f"Error generating occupancy report: {str(e)}")
            raise

    @staticmethod
    def get_tenant_report(landlord_id, use_cache=False):
        """
        Generate detailed tenant report with optimized queries.
        
        Optimizations:
        - Eager loading of relationships
        - Batch queries for payments
        - Reduced N+1 queries
        
        Args:
            landlord_id: ID of landlord
            use_cache: Whether to use cached results
        
        Returns:
            list: Tenant information
        """
        try:
            db_manager = get_database_manager()
            if db_manager:
                read_session = db_manager.get_read_session()
            else:
                read_session = db.session
            
            try:
                # Get properties efficiently
                properties = read_session.query(Property.id).filter_by(
                    landlord_id=landlord_id
                ).all()
                property_ids = [p[0] for p in properties]
                
                if not property_ids:
                    return []
                
                # Get all tenants with property eagerly loaded
                tenants = read_session.query(Tenant).options(
                    joinedload(Tenant.property)
                ).filter(
                    Tenant.property_id.in_(property_ids)
                ).all()
                
                # Get all tenant IDs
                tenant_ids = [t.id for t in tenants]
                
                # Batch fetch latest payments for all tenants
                latest_payments = {}
                if tenant_ids:
                    for batch in optimizer.batch_query(Payment, tenant_ids):
                        latest_payment = read_session.query(Payment).filter(
                            Payment.tenant_id == batch.tenant_id,
                            Payment.status == 'confirmed'
                        ).order_by(Payment.payment_date.desc()).first()
                        if latest_payment:
                            latest_payments[batch.tenant_id] = latest_payment
                
                # Get current month payments in batch
                today = datetime.utcnow().date()
                current_month_start = today.replace(day=1)
                
                paid_tenants = set()
                if tenant_ids:
                    paid_payments = read_session.query(Payment.tenant_id).filter(
                        Payment.tenant_id.in_(tenant_ids),
                        Payment.payment_date >= current_month_start,
                        Payment.status == 'confirmed'
                    ).distinct().all()
                    paid_tenants = {p[0] for p in paid_payments}
                
                tenant_data = []
                for tenant in tenants:
                    # Calculate due date
                    due_date = current_month_start.replace(
                        day=tenant.due_day_of_month or 1
                    )
                    grace_period = tenant.grace_period_days or 0
                    effective_due_date = due_date + timedelta(days=grace_period)
                    
                    is_overdue = today > effective_due_date
                    payment_exists = tenant.id in paid_tenants
                    
                    latest_payment = latest_payments.get(tenant.id)
                    
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
            
            finally:
                if db_manager:
                    db_manager.close_read_session(read_session)
        
        except Exception as e:
            logger.error(f"Error generating tenant report: {str(e)}")
            raise

    @staticmethod
    def get_payment_report(landlord_id, start_date=None, end_date=None, use_cache=False):
        """
        Generate detailed payment report with eager loading.
        
        Optimizations:
        - Eager loading of tenant and property relationships
        - Single query with joins instead of N+1
        
        Args:
            landlord_id: ID of landlord
            start_date: Report start date
            end_date: Report end date
            use_cache: Whether to use cached results
        
        Returns:
            list: Payment details
        """
        try:
            if not end_date:
                end_date = datetime.utcnow().date()
            if not start_date:
                start_date = end_date.replace(day=1)
            
            db_manager = get_database_manager()
            if db_manager:
                read_session = db_manager.get_read_session()
            else:
                read_session = db.session
            
            try:
                # Get properties
                properties = read_session.query(Property.id).filter_by(
                    landlord_id=landlord_id
                ).all()
                property_ids = [p[0] for p in properties]
                
                if not property_ids:
                    return []
                
                # Get tenant IDs
                tenants = read_session.query(Tenant.id).filter(
                    Tenant.property_id.in_(property_ids)
                ).all()
                tenant_ids = [t[0] for t in tenants]
                
                if not tenant_ids:
                    return []
                
                # Get payments with eager loading
                payments = read_session.query(Payment).options(
                    joinedload(Payment.tenant).joinedload(Tenant.property)
                ).filter(
                    Payment.tenant_id.in_(tenant_ids),
                    Payment.payment_date >= start_date,
                    Payment.payment_date <= end_date
                ).order_by(Payment.payment_date.desc()).all()
                
                payment_data = []
                for payment in payments:
                    tenant = payment.tenant
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
            
            finally:
                if db_manager:
                    db_manager.close_read_session(read_session)
        
        except Exception as e:
            logger.error(f"Error generating payment report: {str(e)}")
            raise

    @staticmethod
    def get_monthly_revenue_trend(landlord_id, num_months=12):
        """
        Get revenue trend over months.
        
        Args:
            landlord_id: ID of landlord
            num_months: Number of months to include
        
        Returns:
            list: Monthly revenue data
        """
        try:
            db_manager = get_database_manager()
            if db_manager:
                read_session = db_manager.get_read_session()
            else:
                read_session = db.session
            
            try:
                # Get property IDs
                properties = read_session.query(Property.id).filter_by(
                    landlord_id=landlord_id
                ).all()
                property_ids = [p[0] for p in properties]
                
                if not property_ids:
                    return []
                
                # Get tenant IDs
                tenants = read_session.query(Tenant.id).filter(
                    Tenant.property_id.in_(property_ids)
                ).all()
                tenant_ids = [t[0] for t in tenants]
                
                if not tenant_ids:
                    return []
                
                # Query payments grouped by month
                today = datetime.utcnow().date()
                start_date = today.replace(day=1) - timedelta(days=30*num_months)
                
                trends = read_session.query(
                    func.date_trunc('month', Payment.payment_date).label('month'),
                    func.sum(Payment.amount).label('revenue')
                ).filter(
                    Payment.tenant_id.in_(tenant_ids),
                    Payment.payment_date >= start_date,
                    Payment.status == 'confirmed'
                ).group_by('month').order_by('month').all()
                
                return [
                    {
                        'month': trend.month.strftime('%Y-%m') if trend.month else None,
                        'revenue': round(float(trend.revenue) if trend.revenue else 0.0, 2)
                    }
                    for trend in trends
                ]
            
            finally:
                if db_manager:
                    db_manager.close_read_session(read_session)
        
        except Exception as e:
            logger.error(f"Error generating revenue trend: {str(e)}")
            raise

    @staticmethod
    def get_payment_method_distribution(landlord_id):
        """
        Get distribution of payments by method.
        
        Args:
            landlord_id: ID of landlord
        
        Returns:
            dict: Payment method distribution
        """
        try:
            db_manager = get_database_manager()
            if db_manager:
                read_session = db_manager.get_read_session()
            else:
                read_session = db.session
            
            try:
                # Get property and tenant IDs
                properties = read_session.query(Property.id).filter_by(
                    landlord_id=landlord_id
                ).all()
                property_ids = [p[0] for p in properties]
                
                if not property_ids:
                    return {}
                
                tenants = read_session.query(Tenant.id).filter(
                    Tenant.property_id.in_(property_ids)
                ).all()
                tenant_ids = [t[0] for t in tenants]
                
                if not tenant_ids:
                    return {}
                
                # Group payments by method
                distributions = read_session.query(
                    Payment.payment_method,
                    func.count(Payment.id).label('count'),
                    func.sum(Payment.amount).label('total')
                ).filter(
                    Payment.tenant_id.in_(tenant_ids),
                    Payment.status == 'confirmed'
                ).group_by(Payment.payment_method).all()
                
                return {
                    dist.payment_method: {
                        'count': dist.count,
                        'total': round(float(dist.total) if dist.total else 0.0, 2)
                    }
                    for dist in distributions
                }
            
            finally:
                if db_manager:
                    db_manager.close_read_session(read_session)
        
        except Exception as e:
            logger.error(f"Error generating payment method distribution: {str(e)}")
            raise

    @staticmethod
    def clear_cache(pattern=None):
        """
        Clear report cache.
        
        Args:
            pattern: Pattern to match cache keys. If None, clear all report cache.
        """
        if pattern:
            query_cache.invalidate(pattern)
        else:
            query_cache.invalidate(OptimizedReportService.CACHE_PREFIX)
        
        logger.info(f"Cleared report cache for pattern: {pattern or 'all'}")


# Backward compatibility - create alias for existing code
ReportService = OptimizedReportService
