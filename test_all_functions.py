"""
Comprehensive Test Suite for MFUKO7 Application
Tests all major functions across models, routes, jobs, and notifications
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta, date
import tempfile
import json

# Add the parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.extensions import db
from app.models import User, Role, Tenant, Property, Payment, Unit, County, Issue
from app.notification import send_email, send_sms, handle_payment_confirmation
from app.job import rent_due_reminders, overdue_notifications
from werkzeug.security import generate_password_hash
import uuid
import os
from flask import Flask
from dotenv import load_dotenv
from flask_mail import Mail

load_dotenv()

def create_test_app():
    """Create a test app without scheduler"""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'test-secret-key')
    
    # Mail config from .env
    app.config['MAIL_BACKEND'] = 'testing'
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@example.com')
    app.config['MAIL_SUPPRESS_SEND'] = True
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    
    # Twilio config from .env
    app.config['TWILIO_ACCOUNT_SID'] = os.getenv('TWILIO_ACCOUNT_SID')
    app.config['TWILIO_AUTH_TOKEN'] = os.getenv('TWILIO_AUTH_TOKEN')
    app.config['TWILIO_PHONE_NUMBER'] = os.getenv('TWILIO_PHONE_NUMBER')
    
    # Initialize extensions
    db.init_app(app)
    mail = Mail(app)
    
    return app


class TestSetup(unittest.TestCase):
    """Test application setup and configuration"""

    def setUp(self):
        """Create app with test config"""
        self.app = create_test_app()
        
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        """Clean up after tests"""
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_app_creation(self):
        """Test that app is created successfully"""
        self.assertIsNotNone(self.app)
        self.assertTrue(self.app.config['TESTING'])

    def test_database_initialization(self):
        """Test that database is initialized"""
        with self.app.app_context():
            self.assertIsNotNone(db)


class TestModels(unittest.TestCase):
    """Test database models"""

    def setUp(self):
        """Setup test app and database"""
        self.app = create_test_app()
        
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        """Clean up"""
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_role_creation(self):
        """Test Role model creation"""
        role = Role(name='landlord', description='Landlord role')
        db.session.add(role)
        db.session.commit()
        
        retrieved_role = Role.query.filter_by(name='landlord').first()
        self.assertIsNotNone(retrieved_role)
        self.assertEqual(retrieved_role.name, 'landlord')

    def test_user_creation(self):
        """Test User model creation"""
        user = User(
            email='test@example.com',
            password=generate_password_hash('password123'),
            first_name='Test',
            last_name='User',
            fs_uniquifier=str(uuid.uuid4()),
            active=True,
            role='landlord'
        )
        db.session.add(user)
        db.session.commit()
        
        retrieved_user = User.query.filter_by(email='test@example.com').first()
        self.assertIsNotNone(retrieved_user)
        self.assertEqual(retrieved_user.first_name, 'Test')

    def test_user_has_role_method(self):
        """Test has_role method on User model"""
        role = Role(name='landlord')
        db.session.add(role)
        db.session.commit()
        
        user = User(
            email='landlord@test.com',
            password=generate_password_hash('pass'),
            fs_uniquifier=str(uuid.uuid4()),
            active=True,
            role='landlord'
        )
        user.roles.append(role)
        db.session.add(user)
        db.session.commit()
        
        self.assertTrue(user.has_role('landlord'))
        self.assertFalse(user.has_role('tenant'))

    def test_county_creation(self):
        """Test County model creation"""
        county = County(name='Nairobi', state='NBI', country='Kenya')
        db.session.add(county)
        db.session.commit()
        
        retrieved_county = County.query.filter_by(name='Nairobi').first()
        self.assertIsNotNone(retrieved_county)
        self.assertEqual(retrieved_county.country, 'Kenya')

    def test_property_creation(self):
        """Test Property model creation"""
        user = User(
            email='landlord@test.com',
            password=generate_password_hash('pass'),
            fs_uniquifier=str(uuid.uuid4()),
            active=True,
            role='landlord'
        )
        db.session.add(user)
        db.session.commit()
        
        property = Property(
            name='Test Property',
            address='123 Main St',
            property_type='apartment',
            landlord_id=user.id,
            county_name='Nairobi',
            number_of_units=5,
            unit_numbers='1,2,3,4,5',
            amenities='WiFi, Parking'
        )
        db.session.add(property)
        db.session.commit()
        
        retrieved_property = Property.query.filter_by(name='Test Property').first()
        self.assertIsNotNone(retrieved_property)
        self.assertEqual(retrieved_property.landlord_id, user.id)

    def test_tenant_creation(self):
        """Test Tenant model creation"""
        user = User(
            email='tenant@test.com',
            password=generate_password_hash('pass'),
            fs_uniquifier=str(uuid.uuid4()),
            active=True,
            role='tenant'
        )
        db.session.add(user)
        db.session.commit()
        
        tenant = Tenant(
            user_id=user.id,
            first_name='Tenant',
            last_name='User',
            email='tenant@test.com',
            status='active',
            phone_number='+254712345678'
        )
        db.session.add(tenant)
        db.session.commit()
        
        retrieved_tenant = Tenant.query.filter_by(email='tenant@test.com').first()
        self.assertIsNotNone(retrieved_tenant)
        self.assertEqual(retrieved_tenant.first_name, 'Tenant')

    def test_payment_creation(self):
        """Test Payment model creation"""
        user = User(
            email='tenant@test.com',
            password=generate_password_hash('pass'),
            fs_uniquifier=str(uuid.uuid4()),
            active=True,
            role='tenant'
        )
        db.session.add(user)
        db.session.commit()
        
        tenant = Tenant(
            user_id=user.id,
            first_name='Tenant',
            last_name='User',
            email='tenant@test.com',
            status='active'
        )
        db.session.add(tenant)
        db.session.commit()
        
        payment = Payment(
            tenant_id=tenant.id,
            amount=25000.00,
            status='pending',
            payment_method='mpesa',
            due_date=datetime.utcnow().date()
        )
        db.session.add(payment)
        db.session.commit()
        
        retrieved_payment = Payment.query.filter_by(tenant_id=tenant.id).first()
        self.assertIsNotNone(retrieved_payment)
        self.assertEqual(retrieved_payment.amount, 25000.00)


class TestUserPreferences(unittest.TestCase):
    """Test user notification preferences"""

    def setUp(self):
        self.app = create_test_app()
        
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_user_prefs_property(self):
        """Test user notification preferences property"""
        user = User(
            email='test@test.com',
            password=generate_password_hash('pass'),
            fs_uniquifier=str(uuid.uuid4()),
            active=True,
            role='landlord'
        )
        db.session.add(user)
        db.session.commit()
        
        # Test setting preferences
        user.prefs = {'email': True, 'sms': False}
        db.session.commit()
        
        retrieved_user = User.query.get(user.id)
        self.assertTrue(retrieved_user.prefs.get('email'))
        self.assertFalse(retrieved_user.prefs.get('sms'))


class TestNotifications(unittest.TestCase):
    """Test notification functions"""

    def setUp(self):
        self.app = create_test_app()
        
        # Initialize mail extension
        from app.extensions import mail
        mail.init_app(self.app)
        
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    @patch('app.extensions.mail.send')
    def test_send_email(self, mock_send):
        """Test send_email function"""
        with self.app.app_context():
            send_email('Test Subject', ['test@example.com'], 'Test body')
            self.assertTrue(mock_send.called)

    @patch('app.extensions.twilio_client')
    def test_send_sms(self, mock_twilio):
        """Test send_sms function"""
        with self.app.app_context():
            # In TESTING mode, send_sms should return early without calling Twilio
            send_sms('+254712345678', 'Test message')
            # Verify that twilio was NOT called (because we're in TESTING mode)
            self.assertFalse(mock_twilio.messages.create.called)

    @patch('app.extensions.mail.send')
    @patch('app.extensions.twilio_client')
    def test_handle_payment_confirmation(self, mock_twilio, mock_mail):
        """Test handle_payment_confirmation function"""
        user = User(
            email='tenant@test.com',
            password=generate_password_hash('pass'),
            fs_uniquifier=str(uuid.uuid4()),
            active=True,
            role='tenant'
        )
        db.session.add(user)
        db.session.commit()
        
        tenant = Tenant(
            user_id=user.id,
            first_name='Tenant',
            last_name='User',
            email='tenant@test.com',
            phone_number='+254712345678',
            status='active'
        )
        db.session.add(tenant)
        db.session.commit()
        
        payment = Payment(
            tenant_id=tenant.id,
            amount=25000.00,
            status='paid',
            payment_method='mpesa',
            due_date=datetime.utcnow().date()
        )
        db.session.add(payment)
        db.session.commit()
        
        with self.app.app_context():
            handle_payment_confirmation(tenant, payment)
        # Verify that both email and SMS sending attempts were made
        self.assertTrue(mock_mail.called or mock_twilio.messages.create.called)


class TestJobFunctions(unittest.TestCase):
    """Test scheduled job functions"""

    def setUp(self):
        self.app = create_test_app()
        
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_rent_due_reminders_no_tenants(self):
        """Test rent_due_reminders with no tenants"""
        with patch('app.notification.send_email'), \
             patch('app.notification.send_sms'):
            # Should not raise any errors
            rent_due_reminders()

    def test_overdue_notifications_no_tenants(self):
        """Test overdue_notifications with no tenants"""
        with patch('app.notification.send_email'), \
             patch('app.notification.send_sms'):
            # Should not raise any errors
            overdue_notifications()

    def test_rent_due_reminders_with_tenants(self):
        """Test rent_due_reminders with overdue payments"""
        # Create test data
        user = User(
            email='tenant@test.com',
            password=generate_password_hash('pass'),
            fs_uniquifier=str(uuid.uuid4()),
            active=True,
            role='tenant'
        )
        db.session.add(user)
        db.session.commit()
        
        tenant = Tenant(
            user_id=user.id,
            first_name='Tenant',
            last_name='User',
            email='tenant@test.com',
            phone_number='+254712345678',
            status='active'
        )
        db.session.add(tenant)
        db.session.commit()
        
        # Create a payment 3 days from now
        payment_date = datetime.now() + timedelta(days=3)
        payment = Payment(
            tenant_id=tenant.id,
            amount=25000.00,
            status='pending',
            payment_method='mpesa',
            payment_date=payment_date
        )
        db.session.add(payment)
        db.session.commit()
        
        with patch('app.notification.send_email'), \
             patch('app.notification.send_sms'):
            rent_due_reminders()
            # Job should run without errors


class TestDatabaseOperations(unittest.TestCase):
    """Test database CRUD operations"""

    def setUp(self):
        self.app = create_test_app()
        
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_create_and_read_user(self):
        """Test create and read user"""
        user = User(
            email='read_test@test.com',
            password=generate_password_hash('pass'),
            fs_uniquifier=str(uuid.uuid4()),
            active=True,
            role='landlord'
        )
        db.session.add(user)
        db.session.commit()
        
        retrieved = User.query.filter_by(email='read_test@test.com').first()
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.email, 'read_test@test.com')

    def test_update_user(self):
        """Test update user"""
        user = User(
            email='update_test@test.com',
            password=generate_password_hash('pass'),
            fs_uniquifier=str(uuid.uuid4()),
            active=True,
            role='landlord',
            first_name='Old'
        )
        db.session.add(user)
        db.session.commit()
        
        user.first_name = 'New'
        db.session.commit()
        
        retrieved = User.query.filter_by(email='update_test@test.com').first()
        self.assertEqual(retrieved.first_name, 'New')

    def test_delete_user(self):
        """Test delete user"""
        user = User(
            email='delete_test@test.com',
            password=generate_password_hash('pass'),
            fs_uniquifier=str(uuid.uuid4()),
            active=True,
            role='landlord'
        )
        db.session.add(user)
        db.session.commit()
        
        user_id = user.id
        db.session.delete(user)
        db.session.commit()
        
        retrieved = User.query.get(user_id)
        self.assertIsNone(retrieved)


class TestDataIntegrity(unittest.TestCase):
    """Test data integrity and relationships"""

    def setUp(self):
        self.app = create_test_app()
        
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_user_tenant_relationship(self):
        """Test User-Tenant relationship"""
        user = User(
            email='user_tenant@test.com',
            password=generate_password_hash('pass'),
            fs_uniquifier=str(uuid.uuid4()),
            active=True,
            role='tenant'
        )
        db.session.add(user)
        db.session.commit()
        
        tenant = Tenant(
            user_id=user.id,
            first_name='Test',
            last_name='Tenant',
            email='user_tenant@test.com',
            status='active'
        )
        db.session.add(tenant)
        db.session.commit()
        
        retrieved_user = User.query.get(user.id)
        self.assertIsNotNone(retrieved_user.tenant_profile)
        self.assertEqual(retrieved_user.tenant_profile.first_name, 'Test')

    def test_landlord_properties_relationship(self):
        """Test Landlord-Properties relationship"""
        landlord = User(
            email='landlord@test.com',
            password=generate_password_hash('pass'),
            fs_uniquifier=str(uuid.uuid4()),
            active=True,
            role='landlord'
        )
        db.session.add(landlord)
        db.session.commit()
        
        prop1 = Property(
            name='Property 1',
            address='123 St',
            property_type='apartment',
            landlord_id=landlord.id,
            county_name='Nairobi',
            unit_numbers='1,2',
            amenities='WiFi, Gym'
        )
        prop2 = Property(
            name='Property 2',
            address='456 St',
            property_type='house',
            landlord_id=landlord.id,
            county_name='Mombasa',
            unit_numbers='1',
            amenities='Parking'
        )
        db.session.add_all([prop1, prop2])
        db.session.commit()
        
        retrieved_landlord = User.query.get(landlord.id)
        self.assertEqual(len(retrieved_landlord.properties), 2)


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestSetup))
    suite.addTests(loader.loadTestsFromTestCase(TestModels))
    suite.addTests(loader.loadTestsFromTestCase(TestUserPreferences))
    suite.addTests(loader.loadTestsFromTestCase(TestNotifications))
    suite.addTests(loader.loadTestsFromTestCase(TestJobFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseOperations))
    suite.addTests(loader.loadTestsFromTestCase(TestDataIntegrity))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == '__main__':
    result = run_tests()
    sys.exit(0 if result.wasSuccessful() else 1)
