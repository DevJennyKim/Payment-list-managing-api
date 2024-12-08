import pandas as pd
import re
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient

def validate_iso_code(value, iso_set):
    return value in iso_set

def validate_date(value, format="%Y-%m-%d"):
    try:
        datetime.strptime(value, format)
        return True
    except ValueError:
        return False

def validate_phone_number(value):
    pattern = r'^\+?[1-9]\d{1,14}$'
    return bool(re.match(pattern, value))

def validate_currency_code(value):
    return len(value) == 3 and value.isalpha()

def normalize_and_validate_csv(file_path):
    df = pd.read_csv(file_path)

    iso_countries = {"US", "CA", "KR", "FR", "DE"} 
    iso_currencies = {"USD", "CAD", "KRW", "EUR", "GBP"}  

    df['valid'] = True

    mandatory_fields = [
        "payee_first_name", "payee_last_name", "payee_address_line_1",
        "payee_city", "payee_country", "payee_postal_code", "payee_phone_number",
        "payee_email", "currency", "due_amount"
    ]

    for field in mandatory_fields:
        df['valid'] &= df[field].notnull()

    df['valid'] &= df['payee_country'].apply(lambda x: validate_iso_code(x, iso_countries))
    df['valid'] &= df['payee_due_date'].apply(lambda x: validate_date(x))
    df['valid'] &= df['payee_phone_number'].apply(lambda x: validate_phone_number(x))
    df['valid'] &= df['currency'].apply(lambda x: validate_currency_code(x))
    df['valid'] &= df['due_amount'].apply(lambda x: isinstance(x, (int, float)))

    invalid_rows = df[~df['valid']]
    if not invalid_rows.empty:
        print("Invalid rows detected:")
        print(invalid_rows)

    return df[df['valid']].drop(columns=['valid']).to_dict('records')

file_path = "/upload/payment_information.csv"
valid_records = normalize_and_validate_csv(file_path)
print("Validated Records:")
print(valid_records)


def save_to_mongo(data):
    client = MongoClient("mongodb+srv://admin:admin1234@pay-managing.0r9o4.mongodb.net/?retryWrites=true&w=majority&appName=pay-managing")
    db = client['pay-managing']
    collection = db['payment_records']
    result = collection.insert_many(data)
    print(f"{len(result.inserted_ids)} records inserted into MongoDB.")
