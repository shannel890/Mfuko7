import requests
import os
import base64
from dotenv import load_dotenv
from datetime import datetime, timedelta
from flask import current_app

load_dotenv()

class MpesaAPI:
    """Handler for M-Pesa Daraja API integration."""

    def __init__(self):
        self.access_token = None
        self.token_expiry = None
        self.base_url = "https://api.safaricom.co.ke"
        self.sandbox_url = "https://sandbox.safaricom.co.ke"

        # Load credentials from Flask config
        self.consumer_key = current_app.config.get('MPESA_CONSUMER_KEY')
        self.consumer_secret = current_app.config.get('MPESA_CONSUMER_SECRET')
        self.shortcode = current_app.config.get('MPESA_SHORTCODE')
        self.passkey = current_app.config.get('MPESA_PASSKEY')
        self.callback_url = current_app.config.get('MPESA_CALLBACK_URL')

        # Validate required credentials
        if not all([self.consumer_key, self.consumer_secret, self.shortcode, self.passkey, self.callback_url]):
            current_app.logger.error("One or more M-Pesa credentials are missing in config")
            raise ValueError("M-Pesa credentials are missing")

    def set_access_token(self, token, expires_in=3599):
        """Store the access token and set its expiry time."""
        self.access_token = token
        self.token_expiry = datetime.utcnow() + timedelta(seconds=int(expires_in))  


    def is_token_valid(self):
        return self.access_token and self.token_expiry and datetime.utcnow() < (self.token_expiry - timedelta(seconds=30))

    @property
    def api_url(self):
        return self.sandbox_url if current_app.config.get('MPESA_ENVIRONMENT') == 'sandbox' else self.base_url

    def refresh_token(self):
        try:
            credentials = f"{self.consumer_key}:{self.consumer_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()

            headers = {
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/json"
            }

            response = requests.get(
                f"{self.api_url}/oauth/v1/generate?grant_type=client_credentials",
                headers=headers,
                timeout=30
            )

            current_app.logger.info(f"Token refresh response status: {response.status_code}")

            if response.status_code == 200:
                token_data = response.json()
                self.set_access_token(token_data['access_token'], token_data.get('expires_in', 3599))
                current_app.logger.info("M-Pesa access token refreshed successfully")
                return True
            else:
                current_app.logger.error(f"Token refresh failed: {response.text}")
                return False

        except Exception as e:
            current_app.logger.error(f"Exception while refreshing token: {e}", exc_info=True)
            return False

    def ensure_valid_token(self):
        if not self.is_token_valid():
            current_app.logger.info("Token expired or missing, refreshing...")
            return self.refresh_token()
        return True

    def _generate_password(self, timestamp=None):
        if timestamp is None:
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password_str = f"{self.shortcode}{self.passkey}{timestamp}"
        return base64.b64encode(password_str.encode()).decode()

    def _format_phone_number(self, phone_number):
        """Format phone number to required format (2547XXXXXXXX)."""
        if not phone_number:
            current_app.logger.warning("No phone number provided to _format_phone_number")
            return ""

        phone_number = ''.join(filter(str.isdigit, str(phone_number)))

        if phone_number.startswith('0'):
            return '254' + phone_number[1:]
        elif phone_number.startswith('7'):
            return '254' + phone_number
        elif phone_number.startswith('254') and len(phone_number) == 12:
            return phone_number
        else:
            current_app.logger.warning(f"Unexpected phone number format: {phone_number}")
            return phone_number

        



    def verify_transaction(self, transaction_id):
        if not self.ensure_valid_token():
            current_app.logger.error("Failed to get valid access token for M-Pesa API")
            return False

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = self._generate_password(timestamp)

        payload = {
            'BusinessShortCode': self.shortcode,
            'Password': password,
            'Timestamp': timestamp,
            'CheckoutRequestID': transaction_id
        }

        try:
            response = requests.post(
                f'{self.api_url}/mpesa/stkpushquery/v1/query',
                headers=headers,
                json=payload,
                timeout=30
            )

            current_app.logger.info(f"Transaction query status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                current_app.logger.info(f"Transaction query result: {result}")
                return result.get('ResultCode') == "0"

            current_app.logger.error(f"Transaction query failed: {response.text}")
            return False

        except Exception as e:
            current_app.logger.error(f"Error during transaction verification: {e}", exc_info=True)
            return False

    def initiate_stk_push(self, phone_number, amount, account_reference, transaction_description=None):
        if not self.ensure_valid_token():
            current_app.logger.error("Failed to get valid access token for M-Pesa API")
            return None

        try:
            phone_number = self._format_phone_number(phone_number)
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            password = self._generate_password(timestamp)

            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }

            payload = {
                'BusinessShortCode': self.shortcode,
                'Password': password,
                'Timestamp': timestamp,
                'TransactionType': 'CustomerPayBillOnline',
                'Amount': int(amount),
                'PartyA': phone_number,
                'PartyB': self.shortcode,
                'PhoneNumber': phone_number,
                'CallBackURL': self.callback_url,
                'AccountReference': str(account_reference)[:20],
                'TransactionDesc': str(transaction_description or 'Rent Payment')[:13]
            }

            response = requests.post(
                f'{self.api_url}/mpesa/stkpush/v1/processrequest',
                headers=headers,
                json=payload,
                timeout=30
            )

            current_app.logger.info(f"STK Push status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                current_app.logger.info(f"STK Push response: {result}")
                return result.get('CheckoutRequestID') if result.get('ResponseCode') == "0" else None

            current_app.logger.error(f"STK Push failed: {response.text}")
            return None

        except Exception as e:
            current_app.logger.error(f"Error initiating STK push: {e}", exc_info=True)
            return None



