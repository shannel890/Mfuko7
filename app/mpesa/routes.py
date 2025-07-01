from flask import Blueprint, request, jsonify
from app.mpesa.mpesa_api import lipa_na_mpesa_online
from app.models import Tenant, Payment, Invoice
from app.extensions import db, csrf
from datetime import datetime

main = Blueprint('main', __name__)  # This is your blueprint

@main.route('/pay', methods=['POST'])
def make_payment():
    data = request.get_json()
    amount = data.get("amount")
    phone_number = data.get("phone_number")
    response = lipa_na_mpesa_online(amount, phone_number)
    return jsonify(response)


@main.route('/mpesa/callback', methods=['POST'])
@csrf.exempt  # Correct: csrf is from app.extensions
def mpesa_callback():
    data = request.get_json()
    try:
        result = data['Body']['stkCallback']
        result_code = result['ResultCode']
        result_desc = result['ResultDesc']

        if result_code == 0:
            metadata = result.get("CallbackMetadata", {}).get("Item", [])
            metadata_dict = {item["Name"]: item.get("Value") for item in metadata}

            phone_number = metadata_dict.get("PhoneNumber")
            amount = metadata_dict.get("Amount")
            transaction_id = metadata_dict.get("MpesaReceiptNumber")
            transaction_time = metadata_dict.get("TransactionDate")

            # Match last 9 digits of Safaricom phone
            tenant = Tenant.query.filter(
                Tenant.phone_number.like(f"%{str(phone_number)[-9:]}")
            ).first()

            if tenant:
                invoice = Invoice.query.filter_by(
                    tenant_id=tenant.id, status='pending'
                ).first()

                payment = Payment(
                    tenant_id=tenant.id,
                    amount=amount,
                    payment_method='mpesa',
                    transaction_id=transaction_id,
                    payment_date=datetime.utcnow(),
                    status='confirmed',
                    is_offline=False,
                    invoice_id=invoice.id if invoice else None
                )

                db.session.add(payment)

                if invoice:
                    invoice.amount_due -= amount
                    invoice.status = 'paid' if invoice.amount_due <= 0 else 'partially_paid'

                db.session.commit()

        return jsonify({'ResultCode': 0, 'ResultDesc': 'Accepted'})
    except Exception as e:
        print("Callback processing error:", e)
        return jsonify({'ResultCode': 1, 'ResultDesc': 'Error occurred'})
