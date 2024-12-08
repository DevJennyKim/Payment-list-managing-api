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
  if isinstance(payment['payee_due_date'], str):
    payee_due_date = datetime.strptime(payment['payee_due_date'], "%Y-%m-%d").date() 
  else:
    payee_due_date = datetime.utcfromtimestamp(payment['payee_due_date']).date()

  if payee_due_date == today:
    payment['payee_payment_status'] = "due_now"
  elif payee_due_date< today:
    payment['payee_payment_status'] = "overdue"

  return payment

@app.get("/payments")
def get_payments(
  search: str = Query(None),
  filter_status: str = Query(None),
  skip: int = Query(0, ge=0),
  limit:int = Query(10,le=100)
):
  collection = get_collection("payment_records")

  #search and filtering query
  query = {}
  if search:
    query["$text"] = {"$search":search}
  if filter_status:
    query["payee_payment_status"] = filter_status

  #paging
  payments_cursor = collection.find(query).skip(skip).limit(limit)
  payments = list(payments_cursor)
  
  for payment in payments:
    payment = update_payment_status(payment)
    payment['total_due'] = calculate_total_due(payment)
    payment['_id'] = str(payment['_id'])
  
  return {"payments": payments}

@app.post("/payments")
def create_payment(payment: dict):
  collection = get_collection("payment_records")
  result = collection.insert_one(payment)
  
  return {"inserted_id": str(result.inserted_id)}

