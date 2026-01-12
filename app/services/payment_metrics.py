"""
Optimized Payment Service - Query Utilities

Adds optimized query methods to PaymentService for dashboards and metrics.

Optimizations:
- Read-only sessions for metrics
- Eager loading to prevent N+1 queries
- Batch aggregations
- Query result caching
"""

from flask import current_app
from app.extensions import db
from app.db_utils import get_database_manager, query_cache, optimizer
from app.models import Payment, Tenant, Property
from datetime import datetime, timedelta
from sqlalchemy import func, and_
from sqlalchemy.orm import joinedload
import logging

logger = logging.getLogger(__name__)


class PaymentMetricsService:
    """Optimized metrics for payment operations."""
    
    CACHE_PREFIX = "payment_metrics:"
    METRICS_TTL = 300  # 5 minutes

    @staticmethod
    def get_payment_metrics(landlord_id, use_cache=True):
        """
        Get comprehensive payment metrics for dashboard.
        
        Optimizations:
        - Read-only session
        - Single queries for multiple aggregations
        - Query result caching (5 min)
        
        Args:
            landlord_id: ID of landlord
            use_cache: Whether to use cached results
        
        Returns:
            dict: Payment metrics
        """
        try:
            # Check cache
            cache_key = f"{PaymentMetricsService.CACHE_PREFIX}all:{landlord_id}"
            if use_cache:
                cached = query_cache.get(cache_key)
                if cached:
                    logger.info(f"Cache hit for payment metrics: {landlord_id}")
                    return cached
            
            db_manager = get_database_manager()
            if db_manager:
                read_session = db_manager.get_read_session()
            else:
                read_session = db.session
            
            try:
                # Get landlord's property and tenant IDs
                properties = read_session.query(Property.id).filter_by(
                    landlord_id=landlord_id
                ).all()
                property_ids = [p[0] for p in properties]
                
                if not property_ids:
                    metrics = {
                        'total_payments': 0,
                        'total_amount': 0.0,
                        'confirmed_payments': 0,
                        'confirmed_amount': 0.0,
                        'pending_payments': 0,
                        'pending_amount': 0.0,
                        'overdue_tenants': 0,
                        'average_payment': 0.0,
                        'payment_rate': 0.0
                    }
                    query_cache.set(cache_key, metrics)
                    return metrics
                
                tenants = read_session.query(Tenant.id).filter(
                    Tenant.property_id.in_(property_ids)
                ).all()
                tenant_ids = [t[0] for t in tenants]
                
                if not tenant_ids:
                    metrics = {
                        'total_payments': 0,
                        'total_amount': 0.0,
                        'confirmed_payments': 0,
                        'confirmed_amount': 0.0,
                        'pending_payments': 0,
                        'pending_amount': 0.0,
                        'overdue_tenants': 0,
                        'average_payment': 0.0,
                        'payment_rate': 0.0
                    }
                    query_cache.set(cache_key, metrics)
                    return metrics
                
                # Total payments
                total_payments = read_session.query(func.count(Payment.id)).filter(
                    Payment.tenant_id.in_(tenant_ids)
                ).scalar() or 0
                
                total_amount_result = read_session.query(
                    func.coalesce(func.sum(Payment.amount), 0.0)
                ).filter(
                    Payment.tenant_id.in_(tenant_ids)
                ).scalar()
                total_amount = float(total_amount_result) if total_amount_result else 0.0
                
                # Confirmed payments
                confirmed_payments = read_session.query(func.count(Payment.id)).filter(
                    Payment.tenant_id.in_(tenant_ids),
                    Payment.status == 'confirmed'
                ).scalar() or 0
                
                confirmed_amount_result = read_session.query(
                    func.coalesce(func.sum(Payment.amount), 0.0)
                ).filter(
                    Payment.tenant_id.in_(tenant_ids),
                    Payment.status == 'confirmed'
                ).scalar()
                confirmed_amount = float(confirmed_amount_result) if confirmed_amount_result else 0.0
                
                # Pending payments
                pending_payments = read_session.query(func.count(Payment.id)).filter(
                    Payment.tenant_id.in_(tenant_ids),
                    Payment.status == 'pending'
                ).scalar() or 0
                
                pending_amount_result = read_session.query(
                    func.coalesce(func.sum(Payment.amount), 0.0)
                ).filter(
                    Payment.tenant_id.in_(tenant_ids),
                    Payment.status == 'pending'
                ).scalar()
                pending_amount = float(pending_amount_result) if pending_amount_result else 0.0
                
                # Overdue tenants (today > effective due date with no current month payment)
                today = datetime.utcnow().date()
                current_month_start = today.replace(day=1)
                
                overdue_tenants = read_session.query(func.count(Tenant.id)).filter(
                    Tenant.property_id.in_(property_ids),
                    Tenant.status == 'active'
                ).scalar() or 0
                
                # Count tenants with current month payment
                paid_tenants = read_session.query(func.count(func.distinct(Payment.tenant_id))).filter(
                    Payment.tenant_id.in_(tenant_ids),
                    Payment.payment_date >= current_month_start,
                    Payment.status == 'confirmed'
                ).scalar() or 0
                
                overdue_tenants = overdue_tenants - paid_tenants
                
                # Calculate averages
                average_payment = (total_amount / total_payments) if total_payments > 0 else 0.0
                payment_rate = ((paid_tenants / len(tenant_ids)) * 100) if tenant_ids else 0.0
                
                metrics = {
                    'total_payments': total_payments,
                    'total_amount': round(total_amount, 2),
                    'confirmed_payments': confirmed_payments,
                    'confirmed_amount': round(confirmed_amount, 2),
                    'pending_payments': pending_payments,
                    'pending_amount': round(pending_amount, 2),
                    'overdue_tenants': max(0, overdue_tenants),
                    'average_payment': round(average_payment, 2),
                    'payment_rate': round(payment_rate, 2)
                }
                
                # Cache result
                if use_cache:
                    query_cache.set(cache_key, metrics)
                
                return metrics
            
            finally:
                if db_manager:
                    db_manager.close_read_session(read_session)
        
        except Exception as e:
            logger.error(f"Error getting payment metrics: {str(e)}")
            raise

    @staticmethod
    def get_recent_payments(landlord_id, limit=10):
        """
        Get recent payments with eager loading.
        
        Optimizations:
        - Read-only session
        - Eager loading of relationships
        - Limited result set
        
        Args:
            landlord_id: ID of landlord
            limit: Number of recent payments to return
        
        Returns:
            list: Recent payment records
        """
        try:
            db_manager = get_database_manager()
            if db_manager:
                read_session = db_manager.get_read_session()
            else:
                read_session = db.session
            
            try:
                # Get landlord's property IDs
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
                
                # Get recent payments with eager loading
                payments = read_session.query(Payment).options(
                    joinedload(Payment.tenant).joinedload(Tenant.property)
                ).filter(
                    Payment.tenant_id.in_(tenant_ids)
                ).order_by(
                    Payment.payment_date.desc()
                ).limit(limit).all()
                
                return [
                    {
                        'payment_id': p.id,
                        'tenant': f"{p.tenant.first_name} {p.tenant.last_name}" if p.tenant else 'Unknown',
                        'property': p.tenant.property.name if p.tenant and p.tenant.property else 'N/A',
                        'amount': p.amount,
                        'method': p.payment_method,
                        'date': p.payment_date,
                        'status': p.status
                    }
                    for p in payments
                ]
            
            finally:
                if db_manager:
                    db_manager.close_read_session(read_session)
        
        except Exception as e:
            logger.error(f"Error getting recent payments: {str(e)}")
            raise

    @staticmethod
    def get_payment_by_month(landlord_id, num_months=12):
        """
        Get payment totals by month.
        
        Args:
            landlord_id: ID of landlord
            num_months: Number of months to include
        
        Returns:
            list: Monthly payment data
        """
        try:
            db_manager = get_database_manager()
            if db_manager:
                read_session = db_manager.get_read_session()
            else:
                read_session = db.session
            
            try:
                # Get properties and tenants
                properties = read_session.query(Property.id).filter_by(
                    landlord_id=landlord_id
                ).all()
                property_ids = [p[0] for p in properties]
                
                if not property_ids:
                    return []
                
                tenants = read_session.query(Tenant.id).filter(
                    Tenant.property_id.in_(property_ids)
                ).all()
                tenant_ids = [t[0] for t in tenants]
                
                if not tenant_ids:
                    return []
                
                # Get monthly aggregations
                today = datetime.utcnow().date()
                start_date = today.replace(day=1) - timedelta(days=30*num_months)
                
                monthly_data = read_session.query(
                    func.date_trunc('month', Payment.payment_date).label('month'),
                    func.count(Payment.id).label('count'),
                    func.sum(Payment.amount).label('total')
                ).filter(
                    Payment.tenant_id.in_(tenant_ids),
                    Payment.payment_date >= start_date,
                    Payment.status == 'confirmed'
                ).group_by('month').order_by('month').all()
                
                return [
                    {
                        'month': str(data.month.date()) if data.month else None,
                        'count': data.count,
                        'total': round(float(data.total) if data.total else 0.0, 2)
                    }
                    for data in monthly_data
                ]
            
            finally:
                if db_manager:
                    db_manager.close_read_session(read_session)
        
        except Exception as e:
            logger.error(f"Error getting monthly payments: {str(e)}")
            raise

    @staticmethod
    def clear_cache():
        """Clear all payment metrics cache."""
        query_cache.invalidate(PaymentMetricsService.CACHE_PREFIX)
        logger.info("Cleared payment metrics cache")
