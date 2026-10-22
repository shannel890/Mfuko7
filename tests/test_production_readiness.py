from datetime import date, timedelta
from unittest.mock import Mock, call

import pytest
from google import genai
from sqlalchemy import inspect
from werkzeug.security import check_password_hash

from app import create_app
from app.extensions import db
from app.job import rent_due_reminders
from app.models import NotificationDelivery, Role, Tenant, User


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('SECRET_KEY', 'test-only-signing-key')
    monkeypatch.delenv('CRON_SECRET', raising=False)
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


def test_import_and_startup_do_not_require_provider_credentials_or_create_schema(app):
    assert genai is not None
    with app.app_context():
        assert inspect(db.engine).get_table_names() == []
        db.create_all()
        assert db.session.query(User).count() == 0
    assert 'apscheduler' not in app.extensions


def test_production_requires_signing_key_and_database(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('CRON_SECRET', 'test-cron-secret')
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        create_app()

    monkeypatch.setenv('SECRET_KEY', 'test-only-signing-key')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(RuntimeError, match='DATABASE_URL'):
        create_app()


def test_production_requires_cron_secret(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('SECRET_KEY', 'test-only-signing-key')
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    monkeypatch.delenv('CRON_SECRET', raising=False)
    monkeypatch.delenv('VERCEL', raising=False)
    with pytest.raises(RuntimeError, match='CRON_SECRET'):
        create_app()


def test_postgresql_driver_urls_require_ssl(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg2://user:placeholder@db.example.test/app')
    monkeypatch.setenv('SECRET_KEY', 'test-only-signing-key')
    application = create_app()
    assert application.config['SQLALCHEMY_DATABASE_URI'].endswith('?sslmode=require')


def test_admin_cli_hashes_password_and_is_idempotent(app, monkeypatch):
    passwords = iter(['a-long-test-password', 'a-long-test-password', 'another-test-password', 'another-test-password'])
    monkeypatch.setattr('getpass.getpass', lambda _prompt: next(passwords))
    with app.app_context():
        db.create_all()

    runner = app.test_cli_runner()
    first = runner.invoke(args=['create-admin', '--email', 'admin@example.test'])
    assert first.exit_code == 0, first.output
    with app.app_context():
        user = User.query.one()
        assert user.has_role('admin')
        assert check_password_hash(user.password, 'a-long-test-password')
        saved_hash = user.password

    second = runner.invoke(args=['create-admin', '--email', 'admin@example.test'])
    assert second.exit_code == 0, second.output
    assert 'a-long-test-password' not in first.output
    with app.app_context():
        assert User.query.count() == 1
        assert User.query.one().password == saved_hash


def test_admin_cli_does_not_elevate_existing_account(app, monkeypatch):
    monkeypatch.setattr('getpass.getpass', lambda _prompt: 'a-long-test-password')
    with app.app_context():
        db.create_all()
        user = User(email='ordinary@example.test', password='hashed-elsewhere', role='tenant', fs_uniquifier='ordinary-id')
        db.session.add(user)
        db.session.commit()
    result = app.test_cli_runner().invoke(args=['create-admin', '--email', 'ordinary@example.test'])
    assert result.exit_code != 0
    with app.app_context():
        user = User.query.one()
        assert user.role == 'tenant'
        assert not user.has_role('admin')


def test_cron_endpoint_requires_bearer_secret(app, monkeypatch):
    app.config['CRON_SECRET'] = 'test-cron-secret'
    unauthorized = app.test_client().get('/internal/cron/rent-notifications')
    assert unauthorized.status_code == 401

    reminders = Mock(return_value={'sent': 0, 'failed': 0, 'skipped_paid': 0})
    overdue = Mock(return_value={'sent': 0, 'failed': 0, 'skipped_paid': 0})
    monkeypatch.setattr('app.job.rent_due_reminders', reminders)
    monkeypatch.setattr('app.job.overdue_notifications', overdue)
    authorized = app.test_client().get(
        '/internal/cron/rent-notifications',
        headers={'Authorization': 'Bearer test-cron-secret'},
    )
    assert authorized.status_code == 200
    reminders.assert_called_once_with()
    overdue.assert_called_once_with()


def test_rent_reminder_delivery_is_deduplicated_and_failed_channels_retry(app, monkeypatch):
    today = date(2026, 10, 22)
    with app.app_context():
        db.create_all()
        tenant = Tenant(
            first_name='Test', last_name='Tenant', email='tenant@example.test',
            phone_number='+254700000000', status='active', due_day_of_month=25,
            grace_period_days=5,
        )
        db.session.add(tenant)
        db.session.commit()

    email_send = Mock(side_effect=[RuntimeError('temporary failure'), None])
    sms_send = Mock()
    monkeypatch.setattr('app.job.send_email', email_send)
    monkeypatch.setattr('app.job.send_sms', sms_send)

    first_result = rent_due_reminders(today=today)
    second_result = rent_due_reminders(today=today + timedelta(days=1))
    assert first_result['failed'] == 1
    assert second_result['sent'] == 1
    email_send.assert_has_calls([
        call('Rent Due Reminder', ['tenant@example.test'], 'Hello Test Tenant, your rent is due on 25 October 2026.'),
        call('Rent Due Reminder', ['tenant@example.test'], 'Hello Test Tenant, your rent is due on 25 October 2026.'),
    ])
    sms_send.assert_called_once()
    with app.app_context():
        rows = NotificationDelivery.query.order_by(NotificationDelivery.channel).all()
        assert [(row.channel, row.status, row.attempts) for row in rows] == [
            ('email', 'sent', 2), ('sms', 'sent', 1),
        ]
