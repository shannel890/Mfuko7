from datetime import date
from decimal import Decimal
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Property, Role, Tenant, Unit, User


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('APP_ENV', 'development')
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with application.app_context():
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def landlord(db_session):
    role = Role.query.filter_by(name='landlord').first()
    user = User(
        email='landlord-a@example.com',
        password=generate_password_hash('password'),
        first_name='Landlord',
        last_name='A',
        role='landlord',
        fs_uniquifier='landlord-a-id',
        active=True,
    )
    user.roles.append(role)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def tenant_user(db_session):
    role = Role.query.filter_by(name='tenant').first()
    user = User(
        email='tenant@example.com',
        password=generate_password_hash('password'),
        first_name='Tenant',
        last_name='User',
        role='tenant',
        fs_uniquifier='tenant-user-id',
        active=True,
    )
    user.roles.append(role)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session


def make_property(db_session, landlord, name='Property A'):
    property_obj = Property(
        name=name,
        address='1 Main Street',
        property_type='Apartment',
        number_of_units=1,
        landlord_id=landlord.id,
        county_name='Nairobi',
        unit_numbers='A1',
    )
    db_session.add(property_obj)
    db_session.flush()
    unit = Unit(property_id=property_obj.id, unit_number='A1', rent_amount=15000, status='vacant')
    db_session.add(unit)
    db_session.commit()
    return property_obj, unit


def login(client, email):
    response = client.post('/auth/login', data={'email': email, 'password': 'password'}, follow_redirects=False)
    assert response.status_code == 302


def tenant_form_data(property_id, unit_id, email=' tenant@example.com '):
    return {
        'property_id': property_id,
        'unit_id': unit_id,
        'first_name': 'Tenant',
        'last_name': 'User',
        'email': email,
        'phone_number': '0712345678',
        'national_id': '12345678',
        'status': 'active',
        'rent_amount': '15000.00',
        'due_day_of_month': 1,
        'grace_period_days': 5,
        'lease_start_date': date.today().isoformat(),
        'lease_end_date': '',
        'submit': 'Save Tenant',
    }


def test_existing_user_is_linked_during_allocation(app, db_session, landlord, tenant_user):
    property_obj, unit = make_property(db_session, landlord)
    client = app.test_client()
    login(client, landlord.email)

    response = client.post('/tenants/add', data=tenant_form_data(property_obj.id, unit.id), follow_redirects=False)

    assert response.status_code == 302
    tenant = Tenant.query.one()
    assert tenant.user_id == tenant_user.id
    assert tenant.property_id == property_obj.id
    assert tenant.unit_id == unit.id
    assert tenant.rent_amount == Decimal('15000.00')
    assert unit.status == 'occupied'
    assert tenant.property.landlord.id == landlord.id


def test_allocation_rejects_another_landlords_property(app, db_session, landlord, tenant_user):
    other_landlord = User(
        email='landlord-b@example.com',
        password=generate_password_hash('password'),
        first_name='Landlord',
        last_name='B',
        role='landlord',
        fs_uniquifier='landlord-b-id',
        active=True,
    )
    other_landlord.roles.append(Role.query.filter_by(name='landlord').first())
    db_session.add(other_landlord)
    db_session.commit()
    property_obj, unit = make_property(db_session, other_landlord, 'Property B')
    client = app.test_client()
    login(client, landlord.email)

    response = client.post('/tenants/add', data=tenant_form_data(property_obj.id, unit.id), follow_redirects=False)

    assert response.status_code == 200
    assert Tenant.query.count() == 0
    assert unit.status == 'vacant'


def test_allocation_rejects_another_landlords_unit(app, db_session, landlord, tenant_user):
    property_obj, own_unit = make_property(db_session, landlord)
    other_landlord = User(
        email='landlord-b@example.com',
        password=generate_password_hash('password'),
        first_name='Landlord',
        last_name='B',
        role='landlord',
        fs_uniquifier='landlord-b-id-2',
        active=True,
    )
    other_landlord.roles.append(Role.query.filter_by(name='landlord').first())
    db_session.add(other_landlord)
    db_session.commit()
    other_property, other_unit = make_property(db_session, other_landlord, 'Property B')
    client = app.test_client()
    login(client, landlord.email)

    response = client.post(
        '/tenants/add',
        data=tenant_form_data(property_obj.id, other_unit.id),
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert Tenant.query.count() == 0
    assert own_unit.status == 'vacant'
    assert other_unit.status == 'vacant'


def test_registration_links_allocated_tenant_without_duplicate(app, db_session, landlord):
    property_obj, unit = make_property(db_session, landlord)
    allocated = Tenant(
        first_name='Tenant',
        last_name='User',
        email='tenant@example.com',
        property_id=property_obj.id,
        unit_id=unit.id,
        rent_amount=15000,
        landlord_id=landlord.id,
        status='active',
    )
    unit.status = 'occupied'
    db_session.add(allocated)
    db_session.commit()
    client = app.test_client()

    response = client.post('/auth/register', data={
        'first_name': 'Tenant',
        'last_name': 'User',
        'email': ' TENANT@example.com ',
        'password': 'password',
        'confirm_password': 'password',
        'role': 'tenant',
    }, follow_redirects=False)

    assert response.status_code == 302
    assert Tenant.query.count() == 1
    registered_user = User.query.filter_by(email='tenant@example.com').one()
    tenant = Tenant.query.one()
    assert tenant.user_id == registered_user.id
    assert tenant.property_id == property_obj.id
    assert tenant.unit_id == unit.id
    assert tenant.rent_amount == Decimal('15000.00')


def test_dashboard_uses_allocated_tenant_without_creating_duplicate(app, db_session, landlord, tenant_user):
    property_obj, unit = make_property(db_session, landlord)
    tenant = Tenant(
        user_id=None,
        first_name='Tenant',
        last_name='User',
        email=' Tenant@Example.com ',
        property_id=property_obj.id,
        unit_id=unit.id,
        rent_amount=15000,
        landlord_id=landlord.id,
        status='active',
    )
    unit.status = 'occupied'
    db_session.add(tenant)
    db_session.commit()
    client = app.test_client()
    login(client, tenant_user.email)

    response = client.get('/tenant/dashboard')

    assert response.status_code == 200
    assert Tenant.query.count() == 1
    assert Tenant.query.one().user_id == tenant_user.id
    assert property_obj.name.encode() in response.data
    assert unit.unit_number.encode() in response.data
    assert b'15,000' in response.data


def test_tenant_dashboard_does_not_accept_landlord_override(app, db_session, landlord, tenant_user):
    property_obj, unit = make_property(db_session, landlord)
    tenant = Tenant(
        user_id=tenant_user.id,
        first_name='Tenant',
        last_name='User',
        email=tenant_user.email,
        property_id=property_obj.id,
        unit_id=unit.id,
        rent_amount=15000,
        landlord_id=landlord.id,
        status='active',
    )
    unit.status = 'occupied'
    db_session.add(tenant)
    db_session.commit()
    client = app.test_client()
    login(client, tenant_user.email)

    response = client.post('/tenant/dashboard', data={'landlord_id': 999999}, follow_redirects=False)

    assert response.status_code == 405
    assert Tenant.query.one().landlord_id == landlord.id