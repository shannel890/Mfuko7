# notifications.py
from flask_mail import Message
from app import extensions
from app.extensions import mail
from flask import current_app
from twilio.rest import Client

def send_email(subject, recipients, body):
    with current_app.app_context():
        msg = Message(subject, recipients=recipients, body=body)
        mail.send(msg)

def send_sms(to, body):
    # Do not send SMS in testing mode
    if current_app.config.get('TESTING'):
        return
    
    client = extensions.twilio_client
    if client is None:
        account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
        auth_token = current_app.config.get('TWILIO_AUTH_TOKEN')
        if not account_sid or not auth_token or not current_app.config.get('TWILIO_PHONE_NUMBER'):
            raise RuntimeError('Twilio credentials and sender number must be configured to send SMS.')
        client = Client(account_sid, auth_token)
        extensions.twilio_client = client
    client.messages.create(
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
