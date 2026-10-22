Real Estate Payment Tracker
Overview
A web application designed to help real estate professionals and property owners track payments, manage leases, and monitor financial transactions related to their properties.

Features
Tenant Management: Track tenant information and lease details

Payment Tracking: Record and monitor rental payments

Financial Reporting: Generate reports on income and expenses

Reminder System: Get alerts for upcoming payments

Document Storage: Upload and manage lease agreements and receipts

Multi-User Support: Different access levels for owners, managers, and agents

Technologies Used
Frontend: HTML5, CSS3, JavaScript, Bootstrap

Backend: Python, Flask

Database: PostgreSQL/SQLite

Authentication: Flask-Login

Payment Processing: (Optional integration with Stripe/PayPal)

Installation
Prerequisites
Python 3.10+

PostgreSQL (or SQLite for development)

pip package manager

Setup Instructions
Clone the repository:

bash
git clone https://github.com/yourusername/real-estate-payment-tracker.git
cd real-estate-payment-tracker
Create and activate a virtual environment:

bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
Install dependencies:

bash
pip install -r requirements.txt
Set up environment variables:

bash
cp .env.example .env
Edit .env with your configuration:

text
APP_ENV=development
FLASK_DEBUG=1
SECRET_KEY=your-local-secret-key
Run the application:

bash
python run.py
Access the application at http://127.0.0.1:5000

For local development, the app uses `instance/mfuko.db` (SQLite) unless
`DATABASE_URL` is set. Production requires an explicit `DATABASE_URL` and
`SECRET_KEY`. PostgreSQL URLs automatically use `sslmode=require` unless a mode
is already specified. Application startup never creates or alters the schema.

## Production setup and operations

### Environment variables

Set secrets in the deployment provider's secret manager. `.env.example` contains
placeholders only; never copy production values into Git.

| Variable | Purpose | Required by |
| --- | --- | --- |
| `APP_ENV=production` | Enables production configuration checks | Flask app |
| `SECRET_KEY` | Signs Flask sessions and reset tokens | Flask app |
| `SECURITY_PASSWORD_SALT` | Optional token salt for security integrations | Authentication integrations |
| `DATABASE_URL` | PostgreSQL connection; SSL is required by default | Flask app, migrations |
| `CRON_SECRET` | Authenticates scheduled notification requests | Vercel Cron endpoint |
| `GEMINI_API_KEY` | Gemini API access; only needed for AI chat | AI service |
| `GEMINI_MODEL` | Optional Gemini model selection | AI service |
| `MAIL_SERVER`, `MAIL_PORT` | SMTP server connection | Email notifications |
| `MAIL_USERNAME`, `MAIL_PASSWORD` | SMTP authentication | Email notifications |
| `MAIL_DEFAULT_SENDER` | Sender address for outgoing email | Email notifications |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` | SMS account credentials and sending number | SMS notifications |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in OAuth client | Google OAuth |
| `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET` | Daraja API credentials | M-Pesa payments |
| `MPESA_SHORTCODE`, `MPESA_PASSKEY`, `MPESA_CALLBACK_URL`, `MPESA_ENVIRONMENT` | Daraja payment setup | M-Pesa payments |

### Initial administrator

After applying reviewed migrations, run `flask --app run create-admin` in a
terminal. The command prompts for the account email and reads the password with
terminal echo disabled. Use a unique password of at least 12 characters. The
password is hashed with Werkzeug; the command never resets or elevates an
existing ordinary account. Running it again for an existing administrator
makes no changes. To reset an existing administrator password, use the normal
authenticated password reset flow or a separately reviewed administrative
procedure; do not re-run provisioning with a different password.

### Database migrations and safe deployment

Flask-Migrate and Alembic are configured in `migrations/`. Generate and review
changes with:

```bash
flask --app run db current
flask --app run db migrate -m "describe schema change"
flask --app run db upgrade --sql
```

The checked-in migration chain reflects an existing, previously initialized
schema and is not a fresh-database baseline. For any target, first identify the
Neon project, branch, and database from the provider dashboard and compare its
schema with the migration history. Confirm a Neon restore point or create a
logical backup, then verify restore by restoring to a disposable branch and
checking expected tables and row counts. Record the current Alembic revision.
Inspect generated SQL for drops, table recreation, constraint changes, or data
rewrites; test on the disposable branch; then run `flask --app run db upgrade`
as a separate deployment step before deploying code. Do not use `db stamp`
unless a schema comparison proves that the target already has that exact
revision's effects. Production migration has not been run by this repository
change.

### Scheduled notifications

The Flask app no longer starts APScheduler. `vercel.json` schedules a daily
request to `/internal/cron/rent-notifications` at 06:00 UTC (09:00 in Nairobi).
Vercel sends `Authorization: Bearer <CRON_SECRET>`; requests without the
configured secret are rejected. Both rent reminders and overdue notices run
from that endpoint. A unique database key tracks each tenant, notice type, due
date, and delivery channel, suppressing concurrent or repeated delivery. Failed
attempts are retried on a later invocation; a stale in-progress reservation is
eligible for retry after 30 minutes. Email/SMS providers must be configured in
the deployment dashboard for their respective channels to work.

`app/task.py` also contains helper functions for invoice generation, payment
sync, and other reminders, but no scheduler registration for those functions
exists in this repository. The configured Vercel job runs the two previously
registered rent notification jobs only.

### Credential rotation

Values previously present in local/development configuration and old commits
must be treated as compromised. Rotate/revoke in this order, then update the
deployment secret store and redeploy. Verify each service with a non-production
transaction or provider health check:

1. **Flask signing key**: rotate `SECRET_KEY`; expect existing user sessions and
   reset links to expire, then verify sign-in and password reset.
2. **Neon PostgreSQL**: rotate the database role password in Neon, update
   `DATABASE_URL`, and verify a read-only connection before deployment.
3. **Google AI**: revoke exposed Gemini API keys, issue a replacement, update
   `GEMINI_API_KEY`, and verify an AI request.
4. **SMTP**: revoke the mailbox/app password, replace `MAIL_PASSWORD`, then
   verify a test email.
5. **Twilio**: rotate the Auth Token, update all three Twilio variables, then
   verify a test SMS.
6. **Google OAuth**: rotate the OAuth client secret, update both OAuth values,
   and verify the callback and consent configuration.
7. **M-Pesa Daraja**: rotate consumer credentials and passkey in the Daraja
   portal, update shortcode/passkey/callback settings, then verify in sandbox
   before production.
8. **Cron endpoint**: generate a fresh `CRON_SECRET`, update Vercel, and verify
   that authenticated calls succeed and unauthenticated calls return 401.

Two M-Pesa values were removed from the tracked `API_ANALYSIS.md` in this
checkout. The repository history also contains prior credential-like
configuration and the reported hard-coded administrator password. Rotation
alone does not remove historical copies. History cleanup and a coordinated
force-push may be needed for private/shared clones; that rewrite has not been
performed. Existing
production administrator accounts are preserved and require an operator-led
review and password reset if the old account is present.

Usage
Registration: Create an account as a property owner or manager

Add Properties: Enter property details in the dashboard

Add Tenants: Register tenants and assign them to properties

Record Payments: Log rental payments and other transactions

Generate Reports: View financial reports and payment history

Screenshots
(Add screenshots of your application here)

API Documentation
(If applicable, include API documentation here)

Contributing
Fork the repository

Create your feature branch (git checkout -b feature/AmazingFeature)

Commit your changes (git commit -m 'Add some AmazingFeature')

Push to the branch (git push origin feature/AmazingFeature)

Open a Pull Request

License
This project is licensed under the MIT License - see the LICENSE file for details.

Contact
For questions or support, please contact:

Shannel Kirui - shannelkirui739@gmail.com

Project Link: https://github.com/yourusername/real-estate-payment-tracker
