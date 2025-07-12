# app/tasks.py
import requests
from datetime import datetime, timedelta
from sqlalchemy import func, and_
import json

from flask_babel import lazy_gettext as _l

from app.models import Tenant, Property, Payment, User, AuditLog
from app.extensions import db
from app.mpesa.mpesa_api import mpesa_api
from app.notification import send_email, send_sms

# All task functions will now accept 'app' as their first argument
def refresh_mpesa_token(app):
    """
    Periodically refreshes the M-Pesa access token using Safaricom Daraja API.
    """
    with app.app_context():
        consumer_key = app.config.get('MPESA_CONSUMER_KEY')
        consumer_secret = app.config.get('MPESA_CONSUMER_SECRET')
        auth_url = app.config.get('MPESA_AUTH_URL', 'https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials')

        if not consumer_key or not consumer_secret:
            app.logger.error("M-Pesa credentials missing: CONSUMER_KEY or CONSUMER_SECRET not found in config.")
            return

        try:
            response = requests.get(auth_url, auth=requests.auth.HTTPBasicAuth(consumer_key, consumer_secret))
            response.raise_for_status()
            data = response.json()

            access_token = data.get('access_token')
            expires_in = data.get('expires_in', 3599)

            if access_token:
                app.config['MPESA_ACCESS_TOKEN'] = access_token
                app.config['MPESA_TOKEN_EXPIRATION'] = datetime.utcnow() + timedelta(seconds=expires_in)
                app.logger.info("M-Pesa access token refreshed.")

                if hasattr(mpesa_api, 'set_access_token'):
                    mpesa_api.set_access_token(access_token, expires_in=expires_in)
            else:
                app.logger.warning(f"M-Pesa token response did not include access_token: {data}")

        except requests.exceptions.RequestException as e:
            app.logger.error(f"M-Pesa token refresh failed: {e}", exc_info=True)
        except json.JSONDecodeError:
            app.logger.error(f"Invalid JSON in M-Pesa token response: {response.text}", exc_info=True)
        except Exception as e:
            app.logger.error(f"Unexpected error during token refresh: {e}", exc_info=True)

def check_and_generate_rent_invoices(app):
    """
    Generate rent invoices (Payment records) for all active tenants on the 1st of the month.
    This task should typically run once at the beginning of each month.
    """
    with app.app_context():
        try:
            today = datetime.utcnow().date()
            tenants = Tenant.query.filter_by(status='active').all()

            for tenant in tenants:
                if not tenant.due_day_of_month:
                    app.logger.warning(f"Tenant {tenant.id} has no due_day_of_month set. Skipping invoice generation.")
                    continue

                # Calculate the start of the current month and the next month for the payment date range check
                current_month_start = today.replace(day=1)
                if today.month == 12:
                    next_month_start = datetime(today.year + 1, 1, 1).date()
                else:
                    next_month_start = datetime(today.year, today.month + 1, 1).date()

                # Determine the effective due day, handling cases where due_day_of_month exceeds days in month
                effective_due_day = tenant.due_day_of_month
                try:
                    # Test if the day is valid for the current month
                    test_date = current_month_start.replace(day=effective_due_day)
                except ValueError:
                    # If not, set it to the last day of the current month
                    last_day_of_current_month = (next_month_start - timedelta(days=1)).day
                    effective_due_day = last_day_of_current_month

                payment_due_date = datetime(today.year, today.month, effective_due_day).date()


                # Check if a rent payment record already exists for this tenant for the current month
                exists = Payment.query.filter(
                    and_(
                        Payment.tenant_id == tenant.id,
                        Payment.payment_type == 'rent',
                        Payment.status.in_(['pending_confirmation', 'confirmed']),
                        Payment.payment_date >= current_month_start,
                        Payment.payment_date < next_month_start
                    )
                ).first()

                if not exists:
                    new_payment = Payment(
                        tenant_id=tenant.id,
                        amount=tenant.rent_amount,
                        payment_type='rent',
                        status='pending_confirmation',
                        payment_date=payment_due_date # Use the calculated due date
                    )
                    db.session.add(new_payment)
                    app.logger.info(f"Generated new rent invoice for tenant {tenant.id} for {today.strftime('%B %Y')}.")

                    # Send notification if preferences allow and details are available
                    # Add checks for tenant.user and notification_preferences existance
                    if tenant.email and tenant.user and hasattr(tenant.user, 'notification_preferences') and tenant.user.notification_preferences.get('email', True):
                        send_email(
                            subject=_l("Rent Due for %(month)s", month=today.strftime('%B %Y')),
                            recipient=tenant.email,
                            template='email/rent_due', # Assuming this template exists
                            amount=tenant.rent_amount,
                            due_date=new_payment.payment_date.strftime('%d/%m/%Y'),
                            tenant=tenant
                        )

                    if tenant.phone_number and tenant.user and hasattr(tenant.user, 'notification_preferences') and tenant.user.notification_preferences.get('sms', True):
                        send_sms(
                            to=tenant.phone_number,
                            message=_l("Rent of KSh %(amount).2f is due on %(date)s. Pay to Paybill %(paybill)s, Account: %(property)s-%(unit)s",
                                amount=tenant.rent_amount,
                                date=new_payment.payment_date.strftime('%d/%m/%Y'),
                                paybill=app.config.get('MPESA_PAYBILL', 'YOUR_PAYBILL'), # Provide default
                                property=tenant.property.name if tenant.property else 'N/A',
                                unit=tenant.unit_number if hasattr(tenant, 'unit_number') else tenant.id) # Use unit_number if available, else tenant ID
                        )

            db.session.commit()
            app.logger.info("Successfully generated rent invoices for all active tenants.")
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Failed to generate rent invoices: {e}", exc_info=True)


def send_payment_reminders(app):
    """
    Send payment reminders to tenants for payments that are pending confirmation
    and are within the configured reminder days.
    """
    with app.app_context():
        try:
            today = datetime.utcnow().date()
            # Get reminder days from config, default to [5, 3, 1]
            reminder_days_config = app.config.get('PAYMENT_REMINDER_DAYS', [5, 3, 1])
            # Ensure max_days is at least 0 for the filter
            max_days_for_filter = max(reminder_days_config) if reminder_days_config else 0

            # Get all pending payments whose payment_date is in the future
            # and falls within the maximum reminder window from today.
            pending_payments = Payment.query.filter(
                and_(
                    Payment.status == 'pending_confirmation',
                    Payment.payment_date >= today,
                    Payment.payment_date <= today + timedelta(days=max_days_for_filter)
                )
            ).all()

            for payment in pending_payments:
                days_until_due = (payment.payment_date - today).days

                # Only send if days_until_due matches one of the configured reminder days
                if days_until_due in reminder_days_config:
                    tenant = payment.tenant
                    if not tenant:
                        app.logger.warning(f"Payment {payment.id} has no associated tenant. Skipping reminder.")
                        continue

                    # TODO: Implement a mechanism to prevent sending duplicate reminders for the same payment/period.
                    # This could involve:
                    # - A 'last_reminder_sent_date' on the Payment model.
                    # - A dedicated 'ReminderLog' table storing sent reminders.
                    # - Checking the AuditLog for recent 'REMINDER_SENT' actions for this payment.

                    # Send email reminder
                    if tenant.email and tenant.user and hasattr(tenant.user, 'notification_preferences') and tenant.user.notification_preferences.get('email', True):
                        send_email(
                            subject=_l("Rent Payment Reminder - Due in %(days)d days", days=days_until_due),
                            recipient=tenant.email,
                            template='email/payment_reminder', # Assuming this template exists
                            payment=payment,
                            tenant=tenant,
                            days_until_due=days_until_due
                        )

                    # Send SMS reminder
                    if tenant.phone_number and tenant.user and hasattr(tenant.user, 'notification_preferences') and tenant.user.notification_preferences.get('sms', True):
                        send_sms(
                            to=tenant.phone_number,
                            message=_l("Reminder: Rent payment of KSh %(amount).2f is due in %(days)d days ({due_date}). Pay to Paybill %(paybill)s, Account: %(property)s-%(unit)s",
                                amount=payment.amount,
                                days=days_until_due,
                                due_date=payment.payment_date.strftime('%d/%m/%Y'),
                                paybill=app.config.get('MPESA_PAYBILL', 'YOUR_PAYBILL'),
                                property=tenant.property.name if tenant.property else 'N/A',
                                unit=tenant.unit_number if hasattr(tenant, 'unit_number') else tenant.id)
                        )
                    app.logger.info(f"Sent payment reminder to tenant {tenant.id} for payment {payment.id}.")

            app.logger.info("Finished sending payment reminders.")
        except Exception as e:
            app.logger.error(f"Failed to send payment reminders: {e}", exc_info=True)


def sync_offline_payments(app):
    """
    Syncs offline payments from the database to the main system,
    potentially verifying them with external APIs (like M-Pesa).
    This task should run periodically (e.g., every few minutes).
    """
    with app.app_context(): # Now this app_context is explicitly with the passed app instance
        try:
            # Retrieve pending offline payments, limited by OFFLINE_CACHE_LIMIT
            offline_payments = Payment.query.filter_by(
                is_offline=True,
                sync_status='pending_sync'
            ).limit(app.config.get('OFFLINE_CACHE_LIMIT', 1000)).all()

            if not offline_payments:
                app.logger.info("No offline payments to sync.")
                return

            for payment in offline_payments:
                try:
                    # Verify payment with M-Pesa API if it's an M-Pesa payment and has a transaction ID
                    if payment.payment_method == 'M-Pesa' and payment.transaction_id:
                        # Assuming mpesa_api.verify_transaction handles the API call and response
                        app.logger.info(f"Attempting to verify M-Pesa transaction ID: {payment.transaction_id} for payment {payment.id}")
                        verification_result = mpesa_api.verify_transaction(payment.transaction_id)
                        # TODO: Process verification_result to confirm payment details before setting to 'synced'
                        # For now, assuming successful verification if no error is raised by mpesa_api.verify_transaction

                    payment.sync_status = 'synced'
                    payment.is_offline = False
                    db.session.add(payment)

                    # Create audit log entry for the sync operation
                    # Ensure tenant.user_id is correctly set or derived
                    audit_log = AuditLog(
                        user_id=payment.tenant.user_id if payment.tenant else None, # Link to tenant's user if possible
                        action='PAYMENT_SYNC',
                        table_name='payment',
                        record_id=payment.id,
                        details=f"Payment {payment.id} synced from offline mode (Transaction ID: {payment.transaction_id or 'N/A'})"
                    )
                    db.session.add(audit_log)
                    app.logger.info(f"Successfully synced offline payment {payment.id}.")

                except Exception as sync_error:
                    app.logger.error(f"Failed to sync payment {payment.id}: {sync_error}", exc_info=True)
                    payment.sync_status = 'sync_failed'
                    # Optionally, increment a retry counter on the payment here:
                    # payment.sync_retry_count = (payment.sync_retry_count or 0) + 1
                    db.session.add(payment)
            db.session.commit()
            app.logger.info("Finished syncing offline payments.")
        except Exception as e:
            db.session.rollback() # Rollback in case of a larger error preventing batch commit
            app.logger.error(f"Failed to sync offline payments overall: {e}", exc_info=True)


def send_upcoming_rent_reminders(app):
    """
    Sends SMS/Email reminders to tenants whose rent is due in the next few days.
    Runs daily (e.g., at 6 AM).
    """
    with app.app_context():
        app.logger.info("Running scheduled job: Send upcoming rent reminders.")
        today = datetime.utcnow().date()

        # Days before due date to send upcoming reminders
        # This could be a configurable value from app.config (e.g., 'UPCOMING_REMINDER_DAYS')
        reminder_days_before = app.config.get('UPCOMING_REMINDER_DAYS', 3)

        tenants_to_remind = []
        # Query all active tenants
        for tenant in Tenant.query.filter_by(status='active').all():
            if not tenant.due_day_of_month:
                app.logger.warning(f"Tenant {tenant.id} has no due_day_of_month set. Skipping upcoming reminder.")
                continue

            # Calculate rent due date for the current month
            rent_due_date_this_month = None
            try:
                # Try to get the exact day
                rent_due_date_this_month = today.replace(day=tenant.due_day_of_month)
            except ValueError:
                # If the day is invalid for the current month, set to the last day of the month
                current_month_start = today.replace(day=1)
                if today.month == 12:
                    next_month_start = datetime(today.year + 1, 1, 1).date()
                else:
                    next_month_start = datetime(today.year, today.month + 1, 1).date()
                last_day_of_current_month = (next_month_start - timedelta(days=1)).day
                rent_due_date_this_month = today.replace(day=last_day_of_current_month)
            except Exception as e:
                app.logger.error(f"Error calculating rent_due_date for tenant {tenant.id}: {e}", exc_info=True)
                continue # Skip to next tenant

            if not rent_due_date_this_month: # Should not happen with above logic, but for safety
                continue

            # Check if the due date is in the future AND within the reminder window
            if rent_due_date_this_month > today and \
               (rent_due_date_this_month - today).days <= reminder_days_before:

                # Check if tenant has already made a confirmed payment for this month's cycle
                # (Assumes a payment for the month implies the rent is covered)
                current_month_start = today.replace(day=1)
                if today.month == 12:
                    next_month_start = datetime(today.year + 1, 1, 1).date()
                else:
                    next_month_start = datetime(today.year, today.month + 1, 1).date()

                payment_confirmed = Payment.query.filter(
                    Payment.tenant_id == tenant.id,
                    Payment.payment_date >= current_month_start,
                    Payment.payment_date < next_month_start,
                    Payment.status == 'confirmed'
                ).first()

                # TODO: Implement a more robust duplicate reminder prevention.
                # E.g., check a 'reminders_sent' flag or log for this specific payment period.

                if not payment_confirmed:
                    tenants_to_remind.append(tenant)

        for tenant in tenants_to_remind:
            try:
                # Ensure tenant.property is loaded if accessed directly
                property_name = tenant.property.name if tenant.property else _l('N/A')
                paybill_number = app.config.get('MPESA_PAYBILL', 'YOUR_PAYBILL')
                unit_identifier = tenant.unit_number if hasattr(tenant, 'unit_number') and tenant.unit_number else tenant.id # Use unit_number or tenant ID

                sms_message = _l("Hi {tenant_name}, just a friendly reminder that your rent of KES {amount:.2f} for {property_name} is due on {due_date}. Please pay via M-Pesa PayBill {paybill_number} Account {account_number}. Thank you!",
                                 tenant_name=f"{tenant.first_name} {tenant.last_name}",
                                 amount=tenant.rent_amount,
                                 property_name=property_name,
                                 due_date=rent_due_date_this_month.strftime('%Y-%m-%d'),
                                 paybill_number=paybill_number,
                                 account_number=f"TENANT-{unit_identifier}" # Use unit_identifier
                                )
                send_sms(tenant.phone_number, sms_message)

                # Assuming send_email takes a template, subject, recipient, and context variables
                if tenant.email and tenant.user and hasattr(tenant.user, 'notification_preferences') and tenant.user.notification_preferences.get('email', True):
                    send_email(
                        subject=_l("Upcoming Rent Reminder for {property_name}", property_name=property_name),
                        recipient=tenant.email,
                        template='email/upcoming_rent_reminder', # Assuming this template exists
                        tenant=tenant,
                        amount=tenant.rent_amount,
                        due_date=rent_due_date_this_month.strftime('%Y-%m-%d'),
                        property_name=property_name,
                        paybill_number=paybill_number,
                        account_number=f"TENANT-{unit_identifier}", # Use unit_identifier
                        message_body=sms_message # Can pass the SMS message as part of email body if needed
                    )
                app.logger.info(f"Sent upcoming rent reminder to tenant {tenant.id}.")
            except Exception as e:
                app.logger.error(f"Failed to send upcoming rent reminder to tenant {tenant.id}: {e}", exc_info=True)


def send_overdue_reminders(app):
    """
    Sends SMS/Email reminders to tenants with overdue payments.
    Runs daily (e.g., at 9 AM).
    """
    with app.app_context():
        app.logger.info("Running scheduled job: Send overdue reminders.")
        today = datetime.utcnow().date()

        overdue_tenants = []
        for tenant in Tenant.query.filter_by(status='active').all():
            if not tenant.due_day_of_month or tenant.grace_period_days is None:
                app.logger.warning(f"Tenant {tenant.id} has incomplete due date/grace period info. Skipping overdue reminder.")
                continue

            # Calculate the effective due date (due day + grace period) for the current month
            effective_due_date_this_month = None
            try:
                # Try to get the exact day
                rent_due_date = today.replace(day=tenant.due_day_of_month)
                effective_due_date_this_month = rent_due_date + timedelta(days=tenant.grace_period_days)
            except ValueError:
                # If the due_day_of_month is invalid for the current month, cap it to the last day
                current_month_start = today.replace(day=1)
                if today.month == 12:
                    next_month_start = datetime(today.year + 1, 1, 1).date()
                else:
                    next_month_start = datetime(today.year, today.month + 1, 1).date()
                last_day_of_current_month = (next_month_start - timedelta(days=1)).day
                rent_due_date = today.replace(day=last_day_of_current_month)
                effective_due_date_this_month = rent_due_date + timedelta(days=tenant.grace_period_days)
            except Exception as e:
                app.logger.error(f"Error calculating effective_due_date for tenant {tenant.id}: {e}", exc_info=True)
                continue # Skip to next tenant

            if not effective_due_date_this_month: # Should not happen, but for safety
                continue

            # Check if the payment is overdue (today is past effective due date)
            if today > effective_due_date_this_month:
                # Check if tenant has made a confirmed payment for the current month
                current_month_start = today.replace(day=1)
                if today.month == 12:
                    next_month_start = datetime(today.year + 1, 1, 1).date()
                else:
                    next_month_start = datetime(today.year, today.month + 1, 1).date()

                payment_confirmed = Payment.query.filter(
                    Payment.tenant_id == tenant.id,
                    Payment.payment_date >= current_month_start,
                    Payment.payment_date < next_month_start,
                    Payment.status == 'confirmed'
                ).first()

                # If no confirmed payment, add to overdue list
                # TODO: Implement a robust mechanism to prevent sending duplicate overdue reminders.
                # E.g., a 'last_overdue_reminder_sent_date' on the Tenant or Payment record.
                if not payment_confirmed:
                    overdue_tenants.append(tenant)

        for tenant in overdue_tenants:
            try:
                property_name = tenant.property.name if tenant.property else _l('N/A')
                paybill_number = app.config.get('MPESA_PAYBILL', 'YOUR_PAYBILL')
                unit_identifier = tenant.unit_number if hasattr(tenant, 'unit_number') and tenant.unit_number else tenant.id # Use unit_number or tenant ID

                sms_message = _l("URGENT: Hi {tenant_name}, your rent of KES {amount:.2f} for {property_name} due on {due_date} is now overdue. Please make your payment immediately to M-Pesa PayBill {paybill_number} Account {account_number} to avoid further penalties. Thank you!",
                                 tenant_name=f"{tenant.first_name} {tenant.last_name}",
                                 amount=tenant.rent_amount,
                                 property_name=property_name,
                                 due_date=effective_due_date_this_month.strftime('%Y-%m-%d'),
                                 paybill_number=paybill_number,
                                 account_number=f"TENANT-{unit_identifier}" # Use unit_identifier
                                )

                send_sms(tenant.phone_number, sms_message)

                # Assuming send_email takes a template, subject, recipient, and context variables
                if tenant.email and tenant.user and hasattr(tenant.user, 'notification_preferences') and tenant.user.notification_preferences.get('email', True):
                    send_email(
                        subject=_l("URGENT: Overdue Rent Notice for {property_name}", property_name=property_name),
                        recipient=tenant.email,
                        template='email/overdue_notice', # Assuming this template exists
                        tenant=tenant,
                        amount=tenant.rent_amount,
                        due_date=effective_due_date_this_month.strftime('%Y-%m-%d'),
                        property_name=property_name,
                        paybill_number=paybill_number,
                        account_number=f"TENANT-{unit_identifier}", # Use unit_identifier
                        message_body=sms_message # Can pass the SMS message as part of email body if needed
                    )
                app.logger.warning(f"Sent overdue reminder to tenant {tenant.id}.")
            except Exception as e:
                app.logger.error(f"Failed to send overdue reminder to tenant {tenant.id}: {e}", exc_info=True)

def check_overdue_payments(app):
    """
    This function is a placeholder. You can integrate it with a more comprehensive
    overdue payment tracking and penalty application system.
    For example, you might:
    - Mark payments as 'overdue' in the Payment model.
    - Calculate and apply late fees.
    - Trigger further actions (e.g., escalate to property manager).
    """
    with app.app_context():
        app.logger.info("Running scheduled job: Check overdue payments (placeholder).")
        # Example: Find all payments that are overdue and haven't had a late fee applied
        # overdue_payments_to_process = Payment.query.filter(
        #     Payment.status == 'pending_confirmation',
        #     Payment.payment_date + timedelta(days=app.config.get('PAYMENT_GRACE_PERIOD', 5)) < datetime.utcnow().date(),
        #     Payment.late_fee_applied == False # Assuming a 'late_fee_applied' field
        # ).all()
        #
        # for payment in overdue_payments_to_process:
        #     try:
        #         late_fee_amount = payment.amount * app.config.get('PAYMENT_LATE_FEE_PERCENTAGE', 0.05)
        #         # Apply late fee logic here
        #         app.logger.info(f"Applying late fee of {late_fee_amount} to payment {payment.id}.")
        #         # Update payment status or create a new 'late_fee' payment record
        #         # db.session.add(payment)
        #         # db.session.commit()
        #     except Exception as e:
        #         app.logger.error(f"Error applying late fee to payment {payment.id}: {e}")
        # db.session.commit() # Commit all changes