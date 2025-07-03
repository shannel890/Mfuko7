from datetime import date
from flask import current_app
from app.extensions import db
from app.models import Tenant, Invoice
from app.email_utils import send_email
from app.sms_utils import send_sms  # new
import logging

def notify_due_payments():
    today = date.today()
    with current_app.app_context():
        due_invoices = Invoice.query.filter_by(due_date=today).all()
        for invoice in due_invoices:
            tenant = invoice.tenant
            message = f"Dear {tenant.name}, your rent of KES {invoice.amount} is due today. Kindly make payment to avoid penalties."

            # Send Email
            if tenant.email:
                try:
                    send_email(tenant.email, "Rent Payment Due", message)
                except Exception as e:
                    logging.error(f"Failed to email {tenant.email}: {e}")

            # Send SMS
            if tenant.phone_number:
                try:
                    send_sms(tenant.phone_number, message)
                except Exception as e:
                    logging.error(f"Failed to send SMS to {tenant.phone_number}: {e}")
