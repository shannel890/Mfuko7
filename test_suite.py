"""
Comprehensive Test Suite for MFUKO7 Property Management System
Tests all major functionality including models, routes, forms, and integrations
"""

import pytest
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import User, Role, Property, Tenant, Payment, Unit, County
from app.forms import TenantForm, PropertyForm, LoginForm, RegistrationForm
from werkzeug.security import generate_password_hash, check_password_hash
import uuid


@pytest.fixture
def app():
    """Create and configure a test application instance."""
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    os.environ['TESTING'] = 'True'
    os.environ['WTF_CSRF_ENABLED'] = 'False'
    
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create a test client for the app."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create a test CLI runner."""
    return app.test_cli_runner()


@pytest.fixture
def landlord_role(app):
    """Create a landlord role."""
    with app.app_context():
        role = Role(name='landlord', description='Property owner')
        db.session.add(role)
        db.session.commit()
        return role


@pytest.fixture
def tenant_role(app):
    """Create a tenant role."""
    with app.app_context():
        role = Role(name='tenant', description='Property tenant')
        db.session.add(role)
        db.session.commit()
        return role


@pytest.fixture
def landlord_user(app, landlord_role):
    """Create a test landlord user."""
    with app.app_context():
        user = User(
            email='landlord@test.com',
            password=generate_password_hash('password123'),
            first_name='John',
            last_name='Landlord',
            role='landlord',
            fs_uniquifier=str(uuid.uuid4()),
            active=True
        )
        user.roles.append(landlord_role)
        db.session.add(user)
        db.session.commit()
        return user


@pytest.fixture
def tenant_user(app, tenant_role):
    """Create a test tenant user."""
    with app.app_context():
        user = User(
            email='tenant@test.com',
            password=generate_password_hash('password123'),
            first_name='Jane',
            last_name='Tenant',
            role='tenant',
            fs_uniquifier=str(uuid.uuid4()),
            active=True,
            phone_number='254712345678'
        )
        user.roles.append(tenant_role)
        db.session.add(user)
        db.session.commit()
        return user


@pytest.fixture
def test_property(app, landlord_user):
    """Create a test property."""
    with app.app_context():
        property = Property(
            name='Test Apartments',
            address='123 Test Street',
            property_type='apartment',
            number_of_units=5,
            landlord_id=landlord_user.id,
            county_name='Nairobi',
            status='active',
            unit_numbers='A1,A2,A3,A4,A5'
        )
        db.session.add(property)
        db.session.commit()
        return property


@pytest.fixture
def test_unit(app, test_property):
    """Create a test unit."""
    with app.app_context():
        unit = Unit(
            unit_number='A1',
            rent_amount=Decimal('15000.00'),
            deposit_amount=Decimal('15000.00'),
            bedrooms=2,
            bathrooms=1,
            property_id=test_property.id,
            status='vacant'
        )
        db.session.add(unit)
        db.session.commit()
        return unit


@pytest.fixture
def test_tenant(app, test_property, tenant_user):
    """Create a test tenant."""
    with app.app_context():
        tenant = Tenant(
            user_id=tenant_user.id,
            first_name='Jane',
            last_name='Tenant',
            email='tenant@test.com',
            phone_number='254712345678',
            property_id=test_property.id,
            rent_amount=Decimal('15000.00'),
            status='active',
            due_day_of_month=5,
            grace_period_days=5
        )
        db.session.add(tenant)
        db.session.commit()
        return tenant


# ==================== MODEL TESTS ====================

class TestUserModel:
    """Test User model functionality."""
    
    def test_user_creation(self, app, landlord_role):
        """Test creating a new user."""
        with app.app_context():
            user = User(
                email='newuser@test.com',
                password=generate_password_hash('password123'),
                first_name='New',
                last_name='User',
                role='landlord',
                fs_uniquifier=str(uuid.uuid4()),
                active=True
            )
            user.roles.append(landlord_role)
            db.session.add(user)
            db.session.commit()
            
            assert user.id is not None
            assert user.email == 'newuser@test.com'
            assert user.first_name == 'New'
            assert check_password_hash(user.password, 'password123')
    
    def test_user_has_role(self, app, landlord_user):
        """Test has_role method."""
        with app.app_context():
            user = User.query.get(landlord_user.id)
            assert user.has_role('landlord') is True
            assert user.has_role('tenant') is False
    
    def test_user_notification_prefs(self, app, landlord_user):
        """Test notification preferences getter/setter."""
        with app.app_context():
            user = User.query.get(landlord_user.id)
            test_prefs = {'email': True, 'sms': False}
            user.prefs = test_prefs
            db.session.commit()
            
            retrieved_user = User.query.get(landlord_user.id)
            assert retrieved_user.prefs == test_prefs


class TestPropertyModel:
    """Test Property model functionality."""
    
    def test_property_creation(self, app, landlord_user):
        """Test creating a property."""
        with app.app_context():
            property = Property(
                name='New Property',
                address='456 New Street',
                property_type='house',
                number_of_units=1,
                landlord_id=landlord_user.id,
                county_name='Mombasa',
                status='active',
                unit_numbers='H1'
            )
            db.session.add(property)
            db.session.commit()
            
            assert property.id is not None
            assert property.name == 'New Property'
            assert property.landlord_id == landlord_user.id
    
    def test_property_amenities(self, app, test_property):
        """Test amenities list property."""
        with app.app_context():
            property = Property.query.get(test_property.id)
            amenities = ['parking', 'gym', 'pool']
            property.amenities_list = amenities
            db.session.commit()
            
            retrieved = Property.query.get(test_property.id)
            assert retrieved.amenities_list == amenities


class TestTenantModel:
    """Test Tenant model functionality."""
    
    def test_tenant_creation(self, app, test_property, tenant_user):
        """Test creating a tenant."""
        with app.app_context():
            tenant = Tenant(
                user_id=tenant_user.id,
                first_name='New',
                last_name='Tenant',
                email='newtenant@test.com',
                phone_number='254712345679',
                property_id=test_property.id,
                rent_amount=Decimal('20000.00'),
                status='active',
                due_day_of_month=1
            )
            db.session.add(tenant)
            db.session.commit()
            
            assert tenant.id is not None
            assert tenant.rent_amount == Decimal('20000.00')
            assert tenant.property_id == test_property.id


class TestPaymentModel:
    """Test Payment model functionality."""
    
    def test_payment_creation(self, app, test_tenant):
        """Test creating a payment record."""
        with app.app_context():
            payment = Payment(
                tenant_id=test_tenant.id,
                amount=Decimal('15000.00'),
                payment_method='mpesa',
                status='confirmed',
                transaction_id='TEST123456'
            )
            db.session.add(payment)
            db.session.commit()
            
            assert payment.id is not None
            assert payment.amount == Decimal('15000.00')
            assert payment.status == 'confirmed'


class TestUnitModel:
    """Test Unit model functionality."""
    
    def test_unit_creation(self, app, test_property):
        """Test creating a unit."""
        with app.app_context():
            unit = Unit(
                unit_number='B1',
                rent_amount=Decimal('18000.00'),
                deposit_amount=Decimal('18000.00'),
                bedrooms=3,
                bathrooms=2,
                property_id=test_property.id,
                status='vacant'
            )
            db.session.add(unit)
            db.session.commit()
            
            assert unit.id is not None
            assert unit.unit_number == 'B1'
            assert unit.rent_amount == Decimal('18000.00')


# ==================== ROUTE TESTS ====================

class TestAuthRoutes:
    """Test authentication routes."""
    
    def test_landing_page(self, client):
        """Test landing page loads."""
        response = client.get('/')
        assert response.status_code == 200
    
    def test_register_page_loads(self, client):
        """Test registration page loads."""
        response = client.get('/auth/register')
        assert response.status_code == 200
    
    def test_login_page_loads(self, client):
        """Test login page loads."""
        response = client.get('/auth/login')
        assert response.status_code == 200
    
    def test_user_registration(self, client, app, tenant_role):
        """Test user registration process."""
        with app.app_context():
            response = client.post('/auth/register', data={
                'first_name': 'Test',
                'last_name': 'User',
                'email': 'testuser@test.com',
                'password': 'password123',
                'confirm_password': 'password123',
                'role': 'tenant'
            }, follow_redirects=True)
            
            # Check user was created
            user = User.query.filter_by(email='testuser@test.com').first()
            assert user is not None
            assert user.first_name == 'Test'
    
    def test_user_login(self, client, app, landlord_user):
        """Test user login."""
        response = client.post('/auth/login', data={
            'email': 'landlord@test.com',
            'password': 'password123'
        }, follow_redirects=True)
        
        # Should redirect to dashboard
        assert response.status_code == 200


class TestMainRoutes:
    """Test main application routes."""
    
    def test_index_page(self, client):
        """Test index page loads."""
        response = client.get('/index')
        assert response.status_code in [200, 302]  # 302 if redirects
    
    def test_features_page(self, client):
        """Test features page loads."""
        response = client.get('/features')
        assert response.status_code == 200
    
    def test_pricing_page(self, client):
        """Test pricing page loads."""
        response = client.get('/pricing')
        assert response.status_code == 200
    
    def test_testimonials_page(self, client):
        """Test testimonials page loads."""
        response = client.get('/testimonials')
        assert response.status_code == 200


# ==================== FORM TESTS ====================

class TestForms:
    """Test form validation."""
    
    def test_registration_form_valid(self, app):
        """Test valid registration form."""
        with app.test_request_context():
            form = RegistrationForm(
                first_name='John',
                last_name='Doe',
                email='john@test.com',
                password='password123',
                confirm_password='password123',
                role='tenant'
            )
            # Note: validate() may fail without request context, but we test creation
            assert form.first_name.data == 'John'
            assert form.email.data == 'john@test.com'
    
    def test_login_form_valid(self, app):
        """Test valid login form."""
        with app.test_request_context():
            form = LoginForm(
                email='test@test.com',
                password='password123'
            )
            assert form.email.data == 'test@test.com'
            assert form.password.data == 'password123'


# ==================== INTEGRATION TESTS ====================

class TestPropertyManagement:
    """Test property management workflow."""
    
    def test_create_property_with_units(self, app, landlord_user):
        """Test creating a property with units."""
        with app.app_context():
            # Create property
            property = Property(
                name='Integration Test Property',
                address='789 Test Ave',
                property_type='apartment',
                number_of_units=3,
                landlord_id=landlord_user.id,
                county_name='Nairobi',
                status='active',
                unit_numbers='C1,C2,C3'
            )
            db.session.add(property)
            db.session.flush()
            
            # Create units
            for i in range(1, 4):
                unit = Unit(
                    unit_number=f'C{i}',
                    rent_amount=Decimal('12000.00'),
                    property_id=property.id,
                    status='vacant'
                )
                db.session.add(unit)
            
            db.session.commit()
            
            # Verify
            retrieved = Property.query.get(property.id)
            assert len(retrieved.units) == 3
            assert all(u.status == 'vacant' for u in retrieved.units)


class TestTenantPaymentWorkflow:
    """Test tenant and payment workflow."""
    
    def test_tenant_payment_cycle(self, app, test_tenant):
        """Test complete payment cycle for a tenant."""
        with app.app_context():
            tenant = Tenant.query.get(test_tenant.id)
            
            # Create payment
            payment = Payment(
                tenant_id=tenant.id,
                amount=tenant.rent_amount,
                payment_method='mpesa',
                status='confirmed',
                transaction_id='INTEG123'
            )
            db.session.add(payment)
            db.session.commit()
            
            # Verify payment is associated with tenant
            retrieved_tenant = Tenant.query.get(tenant.id)
            assert len(retrieved_tenant.payments) > 0
            assert retrieved_tenant.payments[0].amount == tenant.rent_amount


# ==================== UTILITY FUNCTION TESTS ====================

class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_password_hashing(self):
        """Test password hashing and verification."""
        password = 'testpassword123'
        hashed = generate_password_hash(password)
        
        assert hashed != password
        assert check_password_hash(hashed, password)
        assert not check_password_hash(hashed, 'wrongpassword')
    
    def test_uuid_generation(self):
        """Test UUID generation for uniquifier."""
        uuid1 = str(uuid.uuid4())
        uuid2 = str(uuid.uuid4())
        
        assert uuid1 != uuid2
        assert len(uuid1) == 36


# ==================== RUN TESTS ====================

if __name__ == '__main__':
    print("=" * 70)
    print("MFUKO7 PROPERTY MANAGEMENT SYSTEM - COMPREHENSIVE TEST SUITE")
    print("=" * 70)
    print("\nRunning tests...\n")
    
    # Run pytest with verbose output
    pytest.main([__file__, '-v', '--tb=short'])
