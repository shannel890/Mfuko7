"""
Services module for MFUKO7 application.

Contains business logic layer that separates concerns from route handlers.
Provides clean API for routes to interact with business operations.

Includes optimized services with read/write separation:
- ReportService: Optimized with read-only sessions and caching
- PaymentService: With PaymentMetricsService for dashboard queries
- Other services: Maintain standard implementation
"""

from app.services.payment_service import PaymentService
from app.services.notification_service import NotificationService
from app.services.tenant_service import TenantService
from app.services.report_service import ReportService
from app.services.property_service import PropertyService

# Optimized services with performance improvements
from app.services.optimized_report_service import OptimizedReportService
from app.services.payment_metrics import PaymentMetricsService

__all__ = [
    'PaymentService',
    'NotificationService',
    'TenantService',
    'ReportService',
    'PropertyService',
    'OptimizedReportService',
    'PaymentMetricsService'
]
