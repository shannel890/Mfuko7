import requests
from requests.auth import HTTPBasicAuth
import os
from dotenv import load_dotenv
from datetime import datetime
import base64

load_dotenv()  # Load environment variables from .env file

def get_access_token():
    url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    consumer_key = os.getenv("CONSUMER_KEY")
    consumer_secret = os.getenv("CONSUMER_SECRET")
    response = requests.get(url, auth=HTTPBasicAuth(consumer_key, consumer_secret))
    token = response.json()['access_token']
    return token

def lipa_na_mpesa_online(amount, phone_number):
    access_token = get_access_token()
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    
    business_short_code = '174379'  # Use your shortcode
    passkey = 'YOUR_PASSKEY'        # From M-Pesa portal
    data_to_encode = business_short_code + passkey + timestamp
    password = base64.b64encode(data_to_encode.encode()).decode('utf-8')
    
    api_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "BusinessShortCode": business_short_code,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone_number,
        "PartyB": business_short_code,
        "PhoneNumber": phone_number,
        "CallBackURL": "https://5a3b-2c0f-fe38-2331-71fe-2f4f-5bba-8810-a4df.ngrok.io/callback",
        "AccountReference": "REPT",
        "TransactionDesc": "REPT Rent Payment"
    }

    response = requests.post(api_url, json=payload, headers=headers)
    return response.json()