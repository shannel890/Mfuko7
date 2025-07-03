import requests
from requests.auth import HTTPBasicAuth
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import base64
from flask import current_app

# Load environment variables from .env file
load_dotenv()

class MpesaAPI:
    """Handler for M-Pesa Daraja API integration."""
    
    def __init__(self):
        self.access_token = None
        self.token_expiry = None
        self.base_url = "https://api.safaricom.co.ke"  # Production URL
        self.sandbox_url = "https://sandbox.safaricom.co.ke"  # Sandbox URL

    def set_access_token(self, token, expires_in=3599):
        """Store the access token and set its expiry time."""
        self.access_token = token
        self.token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)

    @property
    def api_url(self):
        """Get the appropriate API URL based on environment."""
        return self.sandbox_url if current_app.config.get('MPESA_ENVIRONMENT') == 'sandbox' else self.base_url

    def _get_credentials(self):
        """Get M-Pesa credentials from app config."""
        return {
            'consumer_key': current_app.config.get('MPESA_CONSUMER_KEY'),
            'consumer_secret': current_app.config.get('MPESA_CONSUMER_SECRET'),
            'shortcode': current_app.config.get('MPESA_SHORTCODE'),
            'passkey': current_app.config.get('MPESA_PASSKEY'),
            'callback_url': current_app.config.get('MPESA_CALLBACK_URL')
        }

    def refresh_token(self):
        """Fetch and set a new access token from M-Pesa."""
        creds = self._get_credentials()
        response = requests.get(
            f"{self.api_url}/oauth/v1/generate?grant_type=client_credentials",
            auth=HTTPBasicAuth(creds['consumer_key'], creds['consumer_secret'])
        )
        if response.status_code == 200:
            token_data = response.json()
            self.set_access_token(
                token_data['access_token'],
                expires_in=token_data.get('expires_in', 3599)
            )
        else:
            current_app.logger.error("Failed to refresh M-Pesa access token")

    def verify_transaction(self, transaction_id):
        """
        Verify an M-Pesa transaction using the Transaction Query API.
        """
        if not self.access_token:
            current_app.logger.error("No access token available for M-Pesa API")
            return False

        creds = self._get_credentials()
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        payload = {
            'BusinessShortCode': creds['shortcode'],
            'Password': self._generate_password(),
            'Timestamp': datetime.now().strftime('%Y%m%d%H%M%S'),
            'CheckoutRequestID': transaction_id
        }

        try:
            response = requests.post(
                f'{self.api_url}/mpesa/stkpushquery/v1/query',
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            current_app.logger.info(f"M-Pesa transaction query response: {result}")

            if result.get('ResultCode') == "0":
                return True
            current_app.logger.warning(f"M-Pesa transaction verification failed: {result}")
            return False

        except Exception as e:
            current_app.logger.error(f"Error verifying M-Pesa transaction: {e}", exc_info=True)
            return False

    def initiate_stk_push(self, phone_number, amount, account_reference, transaction_description=None):
        """
        Initiate an STK Push prompt to the customer's phone.
        """
        if not self.access_token:
            current_app.logger.error("No access token available for M-Pesa API")
            return None

        creds = self._get_credentials()
        if not all(creds.values()):
            current_app.logger.error("Missing required M-Pesa credentials")
            return None

        phone_number = self._format_phone_number(phone_number)

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = self._generate_password()

        payload = {
            'BusinessShortCode': creds['shortcode'],
            'Password': password,
            'Timestamp': timestamp,
            'TransactionType': 'CustomerPayBillOnline',
            'Amount': int(amount),
            'PartyA': phone_number,
            'PartyB': creds['shortcode'],
            'PhoneNumber': phone_number,
            'CallBackURL': creds['callback_url'],
            'AccountReference': account_reference[:20],
            'TransactionDesc': (transaction_description or 'Rent Payment')[:13]
        }

        try:
            response = requests.post(
                f'{self.api_url}/mpesa/stkpush/v1/processrequest',
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            current_app.logger.info(f"STK push response: {result}")

            if result.get('ResponseCode') == "0":
                return result.get('CheckoutRequestID')
            current_app.logger.warning(f"STK push failed: {result}")
            return None

        except Exception as e:
            current_app.logger.error(f"Error initiating STK push: {e}", exc_info=True)
            return None

    def _generate_password(self):
        """Generate the M-Pesa API password."""
        creds = self._get_credentials()
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password_str = f"{creds['shortcode']}{creds['passkey']}{timestamp}"
        return base64.b64encode(password_str.encode()).decode()

    def _format_phone_number(self, phone_number):
        """Format phone number to required format (254XXXXXXXXX)."""
        phone_number = ''.join(filter(str.isdigit, str(phone_number)))
        if phone_number.startswith('0'):
            phone_number = phone_number[1:]
        if not phone_number.startswith('254'):
            phone_number = '254' + phone_number
        return phone_number


# ✅ Optional: standalone fallback function (not needed if using class above)
def get_access_token():
    url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    consumer_key = os.getenv("CONSUMER_KEY")
    consumer_secret = os.getenv("CONSUMER_SECRET")
    response = requests.get(url, auth=HTTPBasicAuth(consumer_key, consumer_secret))
    response.raise_for_status()
    return response.json()['access_token']


# ✅ Initialize the M-Pesa API handler
mpesa_api = MpesaAPI()
