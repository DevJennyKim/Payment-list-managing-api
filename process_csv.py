import pandas as pd
from pymongo import MongoClient
from datetime import datetime

df = pd.read_csv('payment_information.csv')
print(df.head())

df['payee_added_date_utc']=pd.to_datetime(df['payee_added_date_utc'], errors='coerce')
df['payee_due_date'] = pd.to_datetime(df['payee_due_date'], errors='coerce')