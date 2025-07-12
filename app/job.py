# tasks.py
from app.notification import send_sms, send_email
from app.models import Tenant, Payment
from app import scheduler, db
from datetime import datetime, timedelta

def rent_due_reminders():
    today = datetime.today().date()
    reminder_day = today + timedelta(days=3)

    tenants = Tenant.query.join(Payment).filter(
        Payment.due_date == reminder_day,
        Payment.status != 'paid'
    ).all()

    for tenant in tenants:
        subject = "Rent Due Reminder"
        message = f"Dear {tenant.name}, your rent is due on {reminder_day}."
        send_email(subject, [tenant.email], message)
        send_sms(tenant.phone, message)

def overdue_notifications():
    overdue_day = datetime.today().date() - timedelta(days=1)
    tenants = Tenant.query.join(Payment).filter(
        Payment.due_date == overdue_day,
        Payment.status != 'paid'
    ).all()

    for tenant in tenants:
        subject = "Overdue Rent Notice"
        message = f"Hi {tenant.name}, your rent is overdue. Please pay immediately."
        send_email(subject, [tenant.email], message)
        send_sms(tenant.phone, message)

