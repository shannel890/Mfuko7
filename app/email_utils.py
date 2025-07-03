from flask_mail import Message
from app.extensions import mail


def send_email(to, subject, body):
    msg = Message(subject=subject, recipients=[to], body=body)
    mail.send(msg)
