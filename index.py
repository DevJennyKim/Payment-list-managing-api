from fastapi import FastAPI
from db import get_collection

app = FastAPI()

@app.get("/payments")
def get_payments():
    collection = get_collection("payment_records")
    payments = list(collection.find())
    for payment in payments:
      payment['_id'] = str(payment['_id'])
    
    return {"payments": payments}
