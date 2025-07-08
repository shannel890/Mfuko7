import requests
from requests.auth import HTTPBasicAuth
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import base64
from flask import current_app


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

    def is_token_valid(self):
        """Check if the current token is still valid."""
        if not self.access_token or not self.token_expiry:
            return False
        # Add 30 second buffer to prevent edge cases
        return datetime.utcnow() < (self.token_expiry - timedelta(seconds=30))

    @property
    def api_url(self):
        """Get the appropriate API URL based on environment."""
        return self.sandbox_url if current_app.config.get('MPESA_ENVIRONMENT') == 'sandbox' else self.base_url

    def _get_credentials(self):
        key = current_app.config.get('MPESA_CONSUMER_KEY')
        secret = current_app.config.get('MPESA_CONSUMER_SECRET')

        if not key or not secret:
            current_app.logger.error("M-Pesa credentials are missing in config")
            raise ValueError("M-Pesa credentials are missing")
        
        return {
            'consumer_key': key,
            'consumer_secret': secret,
            'shortcode': current_app.config.get('MPESA_SHORTCODE'),
            'passkey': current_app.config.get('MPESA_PASSKEY'),
            'callback_url': current_app.config.get('MPESA_CALLBACK_URL')
        }

    def refresh_token(self):
        """Fetch and set a new access token from M-Pesa."""
        try:
            creds = self._get_credentials()
            consumer_key = creds['consumer_key']
            consumer_secret = creds['consumer_secret']

            # Encode credentials manually
            credentials = f"{consumer_key}:{consumer_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            headers = {
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/json"  # Add Content-Type header
            }

            response = requests.get(
                f"{self.api_url}/oauth/v1/generate?grant_type=client_credentials",
                headers=headers,
                timeout=30  # Add timeout
            )
            
            current_app.logger.info(f"Token refresh response status: {response.status_code}")
            
            if response.status_code == 200:
                token_data = response.json()
                self.set_access_token(
                    token_data['access_token'],
                    expires_in=token_data.get('expires_in', 3599)
                )
                current_app.logger.info("M-Pesa access token refreshed successfully")
                return True
            else:
                current_app.logger.error(
                    f"Failed to refresh M-Pesa access token. Status: {response.status_code}, Body: {response.text}"
                )
                return False
    
        except Exception as e:
            current_app.logger.error(f"Exception while refreshing M-Pesa token: {e}", exc_info=True)
            return False

    def ensure_valid_token(self):
        """Ensure we have a valid token, refresh if necessary."""
        if not self.is_token_valid():
            current_app.logger.info("Token expired or missing, refreshing...")
            return self.refresh_token()
        return True

    def verify_transaction(self, transaction_id):
        """
        Verify an M-Pesa transaction using the Transaction Query API.
        """
        if not self.ensure_valid_token():
            current_app.logger.error("Failed to get valid access token for M-Pesa API")
            return False

        creds = self._get_credentials()

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = self._generate_password(timestamp)

        payload = {
            'BusinessShortCode': creds['shortcode'],
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
            
            current_app.logger.info(f"Transaction query response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                current_app.logger.info(f"M-Pesa transaction query response: {result}")

                if result.get('ResultCode') == "0":
                    return True
                current_app.logger.warning(f"M-Pesa transaction verification failed: {result}")
                return False
            else:
                current_app.logger.error(f"Transaction query failed with status {response.status_code}: {response.text}")
                return False

        except Exception as e:
            current_app.logger.error(f"Error verifying M-Pesa transaction: {e}", exc_info=True)
            return False

    def initiate_stk_push(self, phone_number, amount, account_reference, transaction_description=None):
        """
        Initiate an STK Push prompt to the customer's phone.
        """
        if not self.ensure_valid_token():
            current_app.logger.error("Failed to get valid access token for M-Pesa API")
            return None

        try:
            creds = self._get_credentials()
            if not all([creds['shortcode'], creds['passkey'], creds['callback_url']]):
                current_app.logger.error("Missing required M-Pesa credentials")
                return None

            phone_number = self._format_phone_number(phone_number)

            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }

            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            password = self._generate_password(timestamp)

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
                'AccountReference': str(account_reference)[:20],
                'TransactionDesc': str(transaction_description or 'Rent Payment')[:13]
            }

            response = requests.post(
                f'{self.api_url}/mpesa/stkpush/v1/processrequest',
                headers=headers,
                json=payload,
                timeout=30
            )
            
            current_app.logger.info(f"STK push response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                current_app.logger.info(f"STK push response: {result}")

                if result.get('ResponseCode') == "0":
                    return result.get('CheckoutRequestID')
                current_app.logger.warning(f"STK push failed: {result}")
                return None
            else:
                current_app.logger.error(f"STK push failed with status {response.status_code}: {response.text}")
                return None

        except Exception as e:
            current_app.logger.error(f"Error initiating STK push: {e}", exc_info=True)
            return None

    def _generate_password(self, timestamp=None):
        """Generate the M-Pesa API password."""
        creds = self._get_credentials()
        if timestamp is None:
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


mpesa_api = MpesaAPI()