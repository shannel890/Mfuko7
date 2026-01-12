"""
Notification Service Layer

Handles all notification-related business logic including:
- Sending emails
- Sending SMS messages
- Payment confirmations
- Rent reminders
- Overdue notifications
- Notification preferences management
"""

from flask import current_app
from flask_mail import Message
from app.extensions import mail, twilio_client
from app.models import Tenant, User, Payment
import logging
import json

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for handling notifications (email, SMS)."""

    @staticmethod
    def send_email(subject, recipients, body, html_body=None):
        """
        Send email notification.

        Args:
            subject: Email subject
            recipients: List of email addresses
            body: Plain text body
            html_body: Optional HTML version

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            msg = Message(subject, recipients=recipients, body=body)
            if html_body:
                msg.html = html_body
            mail.send(msg)
            logger.info(f"Email sent to {recipients}")
            return True
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return False

    @staticmethod
    def send_sms(to, body):
        """
        Send SMS notification via Twilio.

        Args:
            to: Phone number to send to
            body: SMS message body

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Don't send SMS in testing mode
            if current_app.config.get('TESTING'):
                logger.info(f"SMS (test mode) to {to}: {body}")
                return False

            message = twilio_client.messages.create(
                to=to,
                from_=current_app.config['TWILIO_PHONE_NUMBER'],
                body=body
            )
            logger.info(f"SMS sent to {to}: {message.sid}")
            return True

        except Exception as e:
            logger.error(f"Error sending SMS to {to}: {str(e)}")
            return False

    @staticmethod
    def handle_payment_confirmation(tenant, payment):
        """
        Send payment confirmation notification to tenant.

        Args:
            tenant: Tenant object
            payment: Payment object

        Returns:
            dict: {email: bool, sms: bool}
        """
        try:
            name = f"{tenant.first_name} {tenant.last_name}"
            email = tenant.email

            message = (
                f"Hi {name}, we've received your rent payment "
                f"of KES {payment.amount}. Thank you!"
            )

            # Send email
            email_sent = NotificationService.send_email(
                "Payment Confirmation",
                [email],
                message
            )

            # Send SMS if phone available
            sms_sent = False
            if tenant.phone_number:
                sms_sent = NotificationService.send_sms(
                    tenant.phone_number,
                    message
                )

            logger.info(
                f"Payment confirmation sent to tenant {tenant.id} "
                f"(email: {email_sent}, sms: {sms_sent})"
            )

            return {'email': email_sent, 'sms': sms_sent}

        except Exception as e:
            logger.error(f"Error sending payment confirmation: {str(e)}")
            return {'email': False, 'sms': False}

    @staticmethod
    def send_rent_reminder(tenant):
        """
        Send rent due reminder to tenant.

        Args:
            tenant: Tenant object

        Returns:
            dict: {email: bool, sms: bool}
        """
        try:
            name = f"{tenant.first_name} {tenant.last_name}"
            email = tenant.email

            message = (
                f"Hi {name}, this is a reminder that your rent "
                f"of KES {tenant.rent_amount} is due on the {tenant.due_day_of_month}th "
                f"of this month. Please make your payment to avoid late fees."
            )

            email_sent = NotificationService.send_email(
                "Rent Due Reminder",
                [email],
                message
            )

            sms_sent = False
            if tenant.phone_number:
                sms_sent = NotificationService.send_sms(
                    tenant.phone_number,
                    message
                )

            logger.info(
                f"Rent reminder sent to tenant {tenant.id} "
                f"(email: {email_sent}, sms: {sms_sent})"
            )

            return {'email': email_sent, 'sms': sms_sent}

        except Exception as e:
            logger.error(f"Error sending rent reminder: {str(e)}")
            return {'email': False, 'sms': False}

    @staticmethod
    def send_overdue_notice(tenant, days_overdue):
        """
        Send overdue payment notice to tenant.

        Args:
            tenant: Tenant object
            days_overdue: Number of days payment is overdue

        Returns:
            dict: {email: bool, sms: bool}
        """
        try:
            name = f"{tenant.first_name} {tenant.last_name}"
            email = tenant.email

            message = (
                f"Hi {name}, your rent payment of KES {tenant.rent_amount} "
                f"is now {days_overdue} days overdue. "
                f"Please make payment immediately to avoid additional penalties."
            )

            email_sent = NotificationService.send_email(
                "Overdue Payment Notice",
                [email],
                message
            )

            sms_sent = False
            if tenant.phone_number:
                sms_sent = NotificationService.send_sms(
                    tenant.phone_number,
                    message
                )

            logger.info(
                f"Overdue notice sent to tenant {tenant.id} "
                f"(email: {email_sent}, sms: {sms_sent})"
            )

            return {'email': email_sent, 'sms': sms_sent}

        except Exception as e:
            logger.error(f"Error sending overdue notice: {str(e)}")
            return {'email': False, 'sms': False}

    @staticmethod
    def get_user_notification_preferences(user_id):
        """
        Get user's notification preferences.

        Args:
            user_id: ID of user

        Returns:
            dict: Notification preferences
        """
        try:
            user = User.query.get(user_id)
            if user and user.notification_preferences:
                return json.loads(user.notification_preferences)
            return {
                'email_enabled': True,
                'sms_enabled': True,
                'payment_reminders': True,
                'overdue_notices': True
            }
        except Exception as e:
            logger.error(f"Error getting notification preferences: {str(e)}")
            return {}

    @staticmethod
    def update_user_notification_preferences(user_id, preferences):
        """
        Update user's notification preferences.

        Args:
            user_id: ID of user
            preferences: Dictionary of preferences

        Returns:
            bool: True if successful
        """
        try:
            user = User.query.get(user_id)
            if user:
                user.notification_preferences = json.dumps(preferences)
                from app.extensions import db
                db.session.commit()
                logger.info(f"Notification preferences updated for user {user_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating notification preferences: {str(e)}")
            return False

    @staticmethod
    def should_send_notification(user_id, notification_type):
        """
        Check if a notification should be sent based on user preferences.

        Args:
            user_id: ID of user
            notification_type: Type of notification (email, sms, etc)

        Returns:
            bool: True if notification should be sent
        """
        try:
            preferences = NotificationService.get_user_notification_preferences(user_id)

            # Check if notifications are generally enabled
            if notification_type == 'email':
                return preferences.get('email_enabled', True)
            elif notification_type == 'sms':
                return preferences.get('sms_enabled', True)

            return True

        except Exception as e:
            logger.error(f"Error checking notification preference: {str(e)}")
            return True  # Default to sending if error

    @staticmethod
    def send_welcome_email(user):
        """
        Send welcome email to new user.

        Args:
            user: User object

        Returns:
            bool: True if successful
        """
        try:
            name = f"{user.first_name} {user.last_name}" if user.first_name else user.email

            subject = "Welcome to MFUKO7"
            body = (
                f"Hi {name},\n\n"
                f"Welcome to MFUKO7! We're excited to have you on board.\n\n"
                f"Log in to your account to get started managing your properties and payments.\n\n"
                f"Best regards,\n"
                f"MFUKO7 Team"
            )

            return NotificationService.send_email(subject, [user.email], body)

        except Exception as e:
            logger.error(f"Error sending welcome email: {str(e)}")
            return False

    @staticmethod
    def send_password_reset_email(user, reset_token):
        """
        Send password reset email to user.

        Args:
            user: User object
            reset_token: Password reset token

        Returns:
            bool: True if successful
        """
        try:
            name = f"{user.first_name} {user.last_name}" if user.first_name else user.email
            reset_link = f"{current_app.config.get('BASE_URL', 'http://localhost:5000')}/auth/reset_password/{reset_token}"

            subject = "Password Reset Request"
            body = (
                f"Hi {name},\n\n"
                f"Click the link below to reset your password:\n"
                f"{reset_link}\n\n"
                f"This link expires in 24 hours.\n\n"
                f"If you didn't request a password reset, ignore this email.\n\n"
                f"Best regards,\n"
                f"MFUKO7 Team"
            )

            return NotificationService.send_email(subject, [user.email], body)

        except Exception as e:
            logger.error(f"Error sending password reset email: {str(e)}")
            return False
