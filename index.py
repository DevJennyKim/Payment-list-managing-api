from fastapi import FastAPI, Query, HTTPException
from datetime import datetime
from db import get_collection
from bson import ObjectId

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
  page: int = Query(1, ge=1),
  limit:int = Query(20, le=100)
):
  collection = get_collection("payment_records")

  #search and filtering query
  query = {}
  if search:
    query["$text"] = {"$search":search}
  if filter_status:
    query["payee_payment_status"] = filter_status

  #paging
  skip = (page-1)*limit

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

@app.delete("/payments/{payment_id}")
def delete_payment(payment_id: str):
  collection = get_collection("payment_records")
  try:
    payment_object_id = ObjectId(payment_id)
  except Exception as e:
    raise HTTPException(status_code=400, detail="Invalid ID format")


  result = collection.delete_one({"_id": payment_object_id})

  if result.deleted_count == 0:
    raise HTTPException(status_code=404, detail="Payment not found")

  return {"message": "Payment deleted successfully"}

@app.put("/payments/{payment_id}")
def update_payment(payment_id: str, payment:dict):
  collection  = get_collection("payment_records")

  try:
    payment_object_id = ObjectId(payment_id)
  except Exception as e:
    raise HTTPException(status_code=400, detail="Invalid ID format")
  
  existing_payment = collection.find_one({"_id": payment_object_id})
  if not existing_payment:
    raise HTTPException(status_code = 404, detail = "Payment not found")
  
  updated_payment = {**existing_payment, **payment}

  updated_payment = update_payment_status(updated_payment)
  updated_payment['total_due'] = calculate_total_due(updated_payment)

  result = collection.replace_one({"_id": payment_object_id}, updated_payment)

  if result.matched_count == 0:
    raise HTTPException(status_code=404, detail="Payment not found")
  
  updated_payment['_id'] = str(updated_payment['_id'])
  
  return {"message": "Payment updated successfully", "updated_payment": updated_payment}