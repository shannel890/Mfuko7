"""Externally invoked, idempotent rent notification jobs."""

import calendar
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import NotificationDelivery, Payment, Tenant
from app.notification import send_email, send_sms


def _due_date(tenant, reference_date, next_occurrence=False):
    due_day = tenant.due_day_of_month or 1
    due_date = date(
        reference_date.year, reference_date.month,
        min(due_day, calendar.monthrange(reference_date.year, reference_date.month)[1]),
    )
    if next_occurrence and due_date < reference_date:
        if reference_date.month == 12:
            year, month = reference_date.year + 1, 1
        else:
            year, month = reference_date.year, reference_date.month + 1
        due_date = date(year, month, min(due_day, calendar.monthrange(year, month)[1]))
    return due_date


def _paid_for_due_month(tenant_id, due_date):
    month_start = due_date.replace(day=1)
    if due_date.month == 12:
        next_month = date(due_date.year + 1, 1, 1)
    else:
        next_month = date(due_date.year, due_date.month + 1, 1)
    return Payment.query.filter(
        Payment.tenant_id == tenant_id,
        Payment.status == 'confirmed',
        Payment.payment_date >= month_start,
        Payment.payment_date < next_month,
    ).first() is not None


def _claim_delivery(tenant, kind, due_date, channel):
    """Reserve a delivery key before sending so concurrent cron calls dedupe."""
    delivery = NotificationDelivery.query.filter_by(
        tenant_id=tenant.id, kind=kind, due_date=due_date, channel=channel
    ).with_for_update().first()
    if delivery is None:
        delivery = NotificationDelivery(
            tenant_id=tenant.id, kind=kind, due_date=due_date,
            channel=channel, status='processing', attempts=1,
        )
        db.session.add(delivery)
        try:
            db.session.commit()
            return delivery
        except IntegrityError:
            db.session.rollback()
            return None
    if delivery.status == 'sent' or delivery.status == 'processing':
        if delivery.status == 'sent':
            return None
        created_at = delivery.created_at
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at and created_at > datetime.now(timezone.utc) - timedelta(minutes=30):
            return None
    delivery.status = 'processing'
    delivery.attempts += 1
    delivery.last_error = None
    db.session.commit()
    return delivery


def _send(tenant, kind, due_date, subject, body):
    sent = 0
    errors = 0
    channels = []
    if tenant.email:
        channels.append(('email', tenant.email))
    if tenant.phone_number:
        channels.append(('sms', tenant.phone_number))
    for channel, target in channels:
        delivery = _claim_delivery(tenant, kind, due_date, channel)
        if delivery is None:
            continue
        try:
            if channel == 'email':
                send_email(subject, [target], body)
            else:
                send_sms(target, body)
            delivery.status = 'sent'
            delivery.sent_at = datetime.now(timezone.utc)
            delivery.last_error = None
            sent += 1
        except Exception as exc:
            # Keep errors out of response bodies and include no recipient data.
            delivery.status = 'failed'
            delivery.last_error = type(exc).__name__[:100]
            errors += 1
        db.session.commit()
    return {'sent': sent, 'failed': errors}


def _run(kind, today=None):
    today = today or date.today()
    sent = 0
    failed = 0
    skipped_paid = 0
    for tenant in Tenant.query.filter_by(status='active').all():
        due_date = _due_date(tenant, today, next_occurrence=(kind == 'rent_reminder'))
        retrying_failed_reminder = False
        if kind == 'rent_reminder':
            failed_delivery = NotificationDelivery.query.filter_by(
                tenant_id=tenant.id, kind=kind, status='failed'
            ).filter(NotificationDelivery.due_date >= today).order_by(
                NotificationDelivery.due_date.asc()
            ).first()
            if failed_delivery:
                due_date = failed_delivery.due_date
                retrying_failed_reminder = True
        if _paid_for_due_month(tenant.id, due_date):
            skipped_paid += 1
            continue
        grace_end = due_date + timedelta(days=tenant.grace_period_days or 0)
        if kind == 'rent_reminder' and due_date != today + timedelta(days=3) and not retrying_failed_reminder:
            continue
        if kind == 'overdue_notice' and today <= grace_end:
            continue
        name = f'{tenant.first_name} {tenant.last_name}'.strip()
        if kind == 'rent_reminder':
            subject = 'Rent Due Reminder'
            body = f'Hello {name}, your rent is due on {due_date:%d %B %Y}.'
        else:
            subject = 'Overdue Rent Notice'
            body = f'Hello {name}, your rent due on {due_date:%d %B %Y} is overdue.'
        result = _send(tenant, kind, due_date, subject, body)
        sent += result['sent']
        failed += result['failed']
    return {'sent': sent, 'failed': failed, 'skipped_paid': skipped_paid}


def rent_due_reminders(today=None):
    return _run('rent_reminder', today=today)


def overdue_notifications(today=None):
    return _run('overdue_notice', today=today)


def notify_due_payments(today=None):
    """Compatibility name for the externally scheduled reminder task."""
    return rent_due_reminders(today=today)
