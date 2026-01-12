"""
Smoke Test for Dashboard and Report Endpoints

Tests optimized services with read/write separation:
- Dashboard metrics (PaymentMetricsService)
- Report generation (OptimizedReportService)
- Caching functionality
"""

import sys
import os

# Configure test environment BEFORE importing app
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['TESTING'] = '1'

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db, scheduler
from app.models import User, Role, Property, Tenant, Payment
from app.services import OptimizedReportService, PaymentMetricsService
from app.db_utils import query_cache, get_database_manager
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global app instance to reuse across tests
_test_app = None

def get_test_app():
    """Get or create test app instance."""
    global _test_app
    if _test_app is None:
        _test_app = create_app()
        # Stop scheduler to avoid conflicts
        try:
            scheduler.shutdown(wait=False)
        except:
            pass
    return _test_app


def test_database_manager():
    """Test database manager initialization."""
    print("\n" + "="*60)
    print("TEST 1: Database Manager Initialization")
    print("="*60)
    
    try:
        app = get_test_app()
        with app.app_context():
            db_manager = get_database_manager()
            
            if db_manager is None:
                print("❌ FAIL: Database manager not initialized")
                return False
            
            print("✅ PASS: Database manager initialized")
            
            # Test read session
            read_session = db_manager.get_read_session()
            print("✅ PASS: Read session created")
            
            # Test write session
            write_session = db_manager.get_write_session()
            print("✅ PASS: Write session created")
            
            # Close sessions
            db_manager.close_read_session(read_session)
            db_manager.close_write_session(write_session)
            print("✅ PASS: Sessions closed successfully")
            
            return True
    
    except Exception as e:
        print(f"❌ FAIL: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_optimized_report_service():
    """Test OptimizedReportService with read-only sessions."""
    print("\n" + "="*60)
    print("TEST 2: Optimized Report Service")
    print("="*60)
    
    try:
        app = get_test_app()
        with app.app_context():
            # Get a landlord user
            landlord = User.query.filter_by(role='landlord').first()
            
            if not landlord:
                print("⚠️  WARNING: No landlord user found. Creating test landlord...")
                landlord_role = Role.query.filter_by(name='landlord').first()
                if not landlord_role:
                    landlord_role = Role(name='landlord')
                    db.session.add(landlord_role)
                    db.session.commit()
                
                from werkzeug.security import generate_password_hash
                import uuid
                landlord = User(
                    email='test_landlord@test.com',
                    password=generate_password_hash('test123'),
                    first_name='Test',
                    last_name='Landlord',
                    fs_uniquifier=str(uuid.uuid4()),
                    active=True,
                    role='landlord',
                    roles=[landlord_role]
                )
                db.session.add(landlord)
                db.session.commit()
                print(f"✅ Created test landlord: {landlord.email}")
            
            landlord_id = landlord.id
            print(f"Testing with landlord ID: {landlord_id}")
            
            # Test 1: Financial Report
            print("\n--- Testing Financial Report ---")
            start_date = datetime.utcnow().date().replace(day=1)
            end_date = datetime.utcnow().date()
            
            financial_report = OptimizedReportService.get_financial_report(
                landlord_id, 
                start_date, 
                end_date,
                use_cache=False  # First call, no cache
            )
            
            print(f"Period: {financial_report['period']}")
            print(f"Total Income: KSh {financial_report['total_income']:,.2f}")
            print(f"Total Due: KSh {financial_report['total_due']:,.2f}")
            print(f"Collection Rate: {financial_report['collection_rate']}%")
            print(f"Payment Count: {financial_report['payment_count']}")
            print(f"Properties: {financial_report['num_properties']}")
            print(f"Tenants: {financial_report['num_tenants']}")
            print("✅ PASS: Financial report generated")
            
            # Test caching
            print("\n--- Testing Cache Hit ---")
            cached_report = OptimizedReportService.get_financial_report(
                landlord_id, 
                start_date, 
                end_date,
                use_cache=True  # Should hit cache
            )
            
            if cached_report == financial_report:
                print("✅ PASS: Cache hit successful (data matches)")
            else:
                print("❌ FAIL: Cache data mismatch")
                return False
            
            # Test 2: Occupancy Report
            print("\n--- Testing Occupancy Report ---")
            occupancy_report = OptimizedReportService.get_occupancy_report(
                landlord_id,
                use_cache=False
            )
            
            print(f"Total Units: {occupancy_report['total_units']}")
            print(f"Occupied Units: {occupancy_report['occupied_units']}")
            print(f"Vacant Units: {occupancy_report['vacant_units']}")
            print(f"Maintenance Units: {occupancy_report['maintenance_units']}")
            print(f"Occupancy Rate: {occupancy_report['occupancy_rate']}%")
            print(f"Vacancy Rate: {occupancy_report['vacancy_rate']}%")
            print("✅ PASS: Occupancy report generated")
            
            # Test 3: Payment Report
            print("\n--- Testing Payment Report ---")
            payment_report = OptimizedReportService.get_payment_report(
                landlord_id,
                start_date,
                end_date
            )
            
            print(f"Total Payments: {len(payment_report)}")
            if payment_report:
                print(f"First Payment: {payment_report[0]}")
            print("✅ PASS: Payment report generated")
            
            # Test 4: Tenant Report
            print("\n--- Testing Tenant Report ---")
            tenant_report = OptimizedReportService.get_tenant_report(landlord_id)
            
            print(f"Total Tenants: {len(tenant_report)}")
            if tenant_report:
                print(f"First Tenant: {tenant_report[0]['name']}")
            print("✅ PASS: Tenant report generated")
            
            return True
    
    except Exception as e:
        print(f"❌ FAIL: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_payment_metrics_service():
    """Test PaymentMetricsService for dashboard."""
    print("\n" + "="*60)
    print("TEST 3: Payment Metrics Service")
    print("="*60)
    
    try:
        app = get_test_app()
        with app.app_context():
            landlord = User.query.filter_by(role='landlord').first()
            
            if not landlord:
                print("⚠️  WARNING: No landlord user found")
                return False
            
            landlord_id = landlord.id
            print(f"Testing with landlord ID: {landlord_id}")
            
            # Test 1: Payment Metrics
            print("\n--- Testing Payment Metrics ---")
            metrics = PaymentMetricsService.get_payment_metrics(
                landlord_id,
                use_cache=False
            )
            
            print(f"Total Payments: {metrics['total_payments']}")
            print(f"Total Amount: KSh {metrics['total_amount']:,.2f}")
            print(f"Confirmed Payments: {metrics['confirmed_payments']}")
            print(f"Confirmed Amount: KSh {metrics['confirmed_amount']:,.2f}")
            print(f"Pending Payments: {metrics['pending_payments']}")
            print(f"Pending Amount: KSh {metrics['pending_amount']:,.2f}")
            print(f"Overdue Tenants: {metrics['overdue_tenants']}")
            print(f"Average Payment: KSh {metrics['average_payment']:,.2f}")
            print(f"Payment Rate: {metrics['payment_rate']}%")
            print("✅ PASS: Payment metrics generated")
            
            # Test 2: Recent Payments
            print("\n--- Testing Recent Payments ---")
            recent = PaymentMetricsService.get_recent_payments(landlord_id, limit=5)
            
            print(f"Recent Payments: {len(recent)}")
            for payment in recent[:3]:  # Show first 3
                print(f"  - {payment['tenant']}: KSh {payment['amount']:,.2f} ({payment['status']})")
            print("✅ PASS: Recent payments retrieved")
            
            # Test 3: Monthly Payments
            print("\n--- Testing Monthly Payment Data ---")
            monthly = PaymentMetricsService.get_payment_by_month(landlord_id, num_months=6)
            
            print(f"Monthly Data Points: {len(monthly)}")
            for month_data in monthly[:3]:  # Show first 3
                print(f"  - {month_data['month']}: {month_data['count']} payments, KSh {month_data['total']:,.2f}")
            print("✅ PASS: Monthly payment data retrieved")
            
            return True
    
    except Exception as e:
        print(f"❌ FAIL: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_cache_statistics():
    """Test cache statistics tracking."""
    print("\n" + "="*60)
    print("TEST 4: Cache Statistics")
    print("="*60)
    
    try:
        app = get_test_app()
        with app.app_context():
            landlord = User.query.filter_by(role='landlord').first()
            
            if not landlord:
                print("⚠️  WARNING: No landlord user found")
                return False
            
            landlord_id = landlord.id
            
            # Clear cache first
            query_cache.invalidate()
            print("Cache cleared")
            
            # First call (cache miss)
            OptimizedReportService.get_financial_report(
                landlord_id,
                use_cache=True
            )
            
            # Second call (cache hit)
            OptimizedReportService.get_financial_report(
                landlord_id,
                use_cache=True
            )
            
            # Get statistics
            stats = query_cache.get_stats()
            
            print(f"\nCache Statistics:")
            print(f"  Hits: {stats['hits']}")
            print(f"  Misses: {stats['misses']}")
            print(f"  Total Requests: {stats['total_requests']}")
            print(f"  Hit Rate: {stats['hit_rate']}%")
            print(f"  Cached Items: {stats['cached_items']}")
            
            if stats['hits'] > 0:
                print("✅ PASS: Cache is working (hits detected)")
            else:
                print("⚠️  WARNING: No cache hits detected")
            
            return True
    
    except Exception as e:
        print(f"❌ FAIL: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_read_only_session_protection():
    """Test that read-only sessions prevent writes."""
    print("\n" + "="*60)
    print("TEST 5: Read-Only Session Protection")
    print("="*60)
    
    try:
        app = get_test_app()
        with app.app_context():
            db_manager = get_database_manager()
            read_session = db_manager.get_read_session()
            
            try:
                # Try to add an object (should fail)
                landlord_role = Role(name='test_role')
                read_session.add(landlord_role)
                print("❌ FAIL: Read-only session allowed add() operation")
                return False
            
            except RuntimeError as e:
                if "read-only session" in str(e).lower():
                    print("✅ PASS: Read-only session correctly prevented write operation")
                    print(f"   Error message: {str(e)}")
                    return True
                else:
                    print(f"❌ FAIL: Unexpected error: {str(e)}")
                    return False
            
            finally:
                db_manager.close_read_session(read_session)
    
    except Exception as e:
        print(f"❌ FAIL: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all smoke tests."""
    print("\n" + "="*60)
    print("SMOKE TEST SUITE: Read/Write Query Separation")
    print("="*60)
    
    results = {
        'Database Manager': test_database_manager(),
        'Optimized Report Service': test_optimized_report_service(),
        'Payment Metrics Service': test_payment_metrics_service(),
        'Cache Statistics': test_cache_statistics(),
        'Read-Only Protection': test_read_only_session_protection()
    }
    
    print("\n" + "="*60)
    print("TEST RESULTS SUMMARY")
    print("="*60)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print("\n" + "="*60)
    print(f"OVERALL: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print("="*60)
    
    return passed == total


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
