from fastapi import FastAPI, Query
from datetime import datetime
from db import get_collection

app = FastAPI()


def calculate_total_due(payment):
  discount_amount=(payment['due_amount']*payment['discount_percent'])/100
  tax_amount = (payment['due_amount']*payment['tax_percent'])/100
  total_due = payment['due_amount'] - discount_amount + tax_amount
  return total_due

def update_payment_status(payment):
  today = datetime.utcnow().date()
  payee_due_date = datetime.utcfromtimestamp(payment['payee_due_date']).date()

  if payee_due_date == today:
    payment['payee_payment_status'] = "due_now"
  elif payee_due_date< today:
    payment['payee_payment_status'] = "overdue"

  return payment

@app.get("/payments")
def get_payments():
  collection = get_collection("payment_records")
  payments = list(collection.find())
  for payment in payments:
    payment['_id'] = str(payment['_id'])
  
  return {"payments": payments}

@app.post("/payments")
def create_payment(payment: dict):
  collection = get_collection("payment_records")
  result = collection.insert_one(payment)
  
  return {"inserted_id": str(result.inserted_id)}

