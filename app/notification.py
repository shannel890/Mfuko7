# notifications.py
from flask_mail import Message
from app.extensions import mail, twilio_client
from flask import current_app

def send_email(subject, recipients, body):
    with current_app.app_context():
        msg = Message(subject, recipients=recipients, body=body)
        mail.send(msg)

def send_sms(to, body):
    twilio_client.messages.create(
        to=to,
        from_=current_app.config['TWILIO_PHONE_NUMBER'],
        body=body
    )

# after M-Pesa confirmation or manual payment
def handle_payment_confirmation(tenant, payment):
    message = f"Hi {tenant.name}, we’ve received your rent payment of {payment.amount}."
    send_email("Payment Confirmation", [tenant.email], message)
    send_sms(tenant.phone, message)
