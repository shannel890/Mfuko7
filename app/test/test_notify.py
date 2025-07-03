import pytest
from datetime import date
from app.models import Tenant, Invoice
from app.job import notify_due_payments
from app import create_app, db

@pytest.fixture
def sample_data(app):
    with app.app_context():
        tenant = Tenant(name="Jane Doe", email="jane@example.com", phone_number="0712345678")
        db.session.add(tenant)
        db.session.commit()

        invoice = Invoice(tenant_id=tenant.id, amount=10000, due_date=date.today())
        db.session.add(invoice)
        db.session.commit()

        yield
        db.session.remove()

def test_notify_due_payments(sample_data, capsys):
    notify_due_payments()
    captured = capsys.readouterr()
    assert "your rent of KES 10000 is due today" in captured.out
