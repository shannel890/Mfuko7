from datetime import date, timedelta
from unittest.mock import Mock

import pytest

from app import create_app
from app.extensions import db
from app.job import notify_due_payments
from app.models import Tenant


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('SECRET_KEY', 'test-only-signing-key')
    application = create_app()
    application.config['TESTING'] = True
    with application.app_context():
        db.create_all()
        due_date = date.today() + timedelta(days=3)
        db.session.add(Tenant(
            first_name='Jane', last_name='Doe', email='jane@example.test',
            phone_number='0712345678', status='active', due_day_of_month=due_date.day,
        ))
        db.session.commit()
        yield application
        db.session.remove()
        db.drop_all()


def test_notify_due_payments(app, monkeypatch):
    email_send = Mock()
    sms_send = Mock()
    monkeypatch.setattr('app.job.send_email', email_send)
    monkeypatch.setattr('app.job.send_sms', sms_send)

    result = notify_due_payments(today=date.today())

    assert result == {'sent': 2, 'failed': 0, 'skipped_paid': 0}
    email_send.assert_called_once()
    sms_send.assert_called_once()
