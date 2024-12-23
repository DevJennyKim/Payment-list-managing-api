import boto3
import httpx
import requests
import os
from fastapi import FastAPI, UploadFile,Query, File, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from db import get_collection
from bson import ObjectId
from botocore.exceptions import NoCredentialsError
from uuid import uuid4
from io import BytesIO

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

  query = {}

  skip = (page-1)*limit

  payments_cursor = collection.find(query).sort("payee_added_date_utc", -1)
  payments = list(payments_cursor)

  
  for payment in payments:
    payment = update_payment_status(payment)
    payment['total_due'] = calculate_total_due(payment)
    payment['_id'] = str(payment['_id'])
    
  if filter_status:
    payments = [payment for payment in payments if payment['payee_payment_status'] == filter_status]

  if search:
    payments = [payment for payment in payments if (
      search.lower() in payment.get('payee_first_name', '').lower() or 
      search.lower() in payment.get('payee_last_name', '').lower()or
      search.lower() in payment.get('payee_email', '').lower())]

  start_index = skip
  end_index = start_index + limit
  paginated_payments = payments[start_index:end_index]
  

  return {"payments": paginated_payments, "totalItems": len(payments)}


@app.get("/payments/{payment_id}")
def get_payment_by_id(payment_id:str):
  collection = get_collection("payment_records")

  payment = collection.find_one({"_id": ObjectId(payment_id)})

  if not payment:
    raise HTTPException(status_code=404, detail = "Payment record not found")
  
  payment = update_payment_status(payment)
  payment['total_due'] = calculate_total_due(payment)
  payment['_id'] = str(payment['_id'])

  return {"payment": payment}


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

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION")

s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)

BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}

def allowed_file(filename:str) -> bool:
  return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_s3(file: UploadFile, payment_id: str):
  try:
    if not allowed_file(file.filename):
      raise HTTPException(status_code=400, detail="Invalid file type. Only PDF, PNG, JPG are allowed.")
    file_name = f"{payment_id}_{uuid4().hex}_{file.filename}"
    s3_client.upload_fileobj(file.file, BUCKET_NAME, file_name)
    return f"https://{BUCKET_NAME}.s3.amazonaws.com/{file_name}"
  except NoCredentialsError:
    raise HTTPException(status_code=403, detail="AWS credentials not available.")
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
  
@app.post("/upload_evidence/{payment_id}")
async def upload_evidence(payment_id: str, file: UploadFile = File(...)):
  file_url = upload_to_s3(file, payment_id)

  collection = get_collection("payment_records")
  payment = collection.find_one({"_id":ObjectId(payment_id)})

  if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

  if payment["payee_payment_status"] == "completed" and "evidence_file_url" in payment:
        raise HTTPException(status_code=400, detail="Evidence file already uploaded and payment status is completed.")
  
  updated = collection.update_one(
        {"_id": ObjectId(payment_id)},
        {"$set": {"payee_payment_status": "completed","evidence_file_url": file_url}}
    )

  if updated.modified_count == 0:
        raise HTTPException(status_code=404, detail="Payment not found or status already updated.")
  
  return {"message": "File uploaded successfully", "file_url": file_url}

@app.get("/download_evidence/{payment_id}")
async def download_evidence(payment_id: str):
  collection = get_collection("payment_records")
  payment = collection.find_one({"_id": ObjectId(payment_id)})

  if not payment:
    raise HTTPException(status_code = 404, detail="Payment not found")
  
  if "evidence_file_url" not in payment:
    raise HTTPException(status_code=404, detail="Evidence file not found")
  
  file_url = payment["evidence_file_url"]

  try: 
    async with httpx.AsyncClient() as client:
      response = await client.get(file_url)
    if response.status_code == 200:
      file_content = BytesIO(response.content)
      file_name = file_url.split('/')[-1]
      return StreamingResponse(file_content, media_type="application/octet-stream", headers={"Content-Disposition": f"attachment; filename={file_name}"})
    else:
      raise HTTPException(status_code=500, detail="Failed to download file from S3")

  except Exception as e:
    raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


