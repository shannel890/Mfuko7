# notifications.py
from flask_mail import Message
from app.extensions import mail, twilio_client
from flask import current_app

def send_email(subject, recipients, body):
    with current_app.app_context():
        msg = Message(subject, recipients=recipients, body=body)
        mail.send(msg)

def send_sms(to, body):
    # Do not send SMS in testing mode
    if current_app.config.get('TESTING'):
        return
    
    twilio_client.messages.create(
        to=to,
        from_=current_app.config['TWILIO_PHONE_NUMBER'],
        body=body
    )

# after M-Pesa confirmation or manual payment
def handle_payment_confirmation(tenant, payment):
    # Use tenant attributes
    name = f"{tenant.first_name} {tenant.last_name}"
    email = tenant.email
    
    message = f"Hi {name}, we've received your rent payment of {payment.amount}."
    send_email("Payment Confirmation", [email], message)
    if tenant.phone_number:
        send_sms(tenant.phone_number, message)
