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
    url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    business_short_code = os.getenv("BUSINESS_SHORTCODE")
    passkey = os.getenv("PASSKEY")

    data_to_encode = business_short_code + passkey + timestamp
    password = base64.b64encode(data_to_encode.encode()).decode('utf-8')

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
        "CallBackURL": os.getenv("CALLBACK_URL"),
        "AccountReference": "REPT",
        "TransactionDesc": "Payment for rent"
    }

    response = requests.post(url, json=payload, headers=headers)
    return response.json()
