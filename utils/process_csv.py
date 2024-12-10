import pandas as pd
import re
import os
import requests
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
mongo_uri = os.getenv("MONGO_URI")



def get_valid_iso_codes_and_currencies():
    url = "https://restcountries.com/v3.1/all"
    response = requests.get(url)
    countries = response.json()
    iso_codes = {country['cca2'] for country in countries if 'cca2' in country}
    iso_currencies = set()
    for country in countries:
        if 'currencies' in country:
            for currency in country['currencies']:
                iso_currencies.add(currency)

    return iso_codes, iso_currencies


valid_iso_codes, valid_iso_currencies = get_valid_iso_codes_and_currencies()


def validate_iso_code(value, iso_set):
    if value not in iso_set:
        print(f"Invalid ISO code: {value}")
    return value in iso_set

def validate_date(value, format="%Y-%m-%d"):
    try:
        datetime.strptime(value, format)
        return True
    except ValueError:
        return False

def validate_phone_number(value):
    value = str(value)
    pattern = r'^\+?[1-9]\d{1,14}$'
    return bool(re.match(pattern, str(value)))

def validate_currency_code(value):
    return value in valid_iso_currencies

def normalize_and_validate_csv(file_path):
    df = pd.read_csv(file_path)

    df['valid'] = True

    mandatory_fields = [
        "payee_first_name", "payee_last_name", "payee_address_line_1",
        "payee_city", "payee_country", "payee_postal_code", "payee_phone_number",
        "payee_email", "currency", "due_amount"
    ]

    for field in mandatory_fields:
        df['valid'] &= df[field].notnull()
        print(f"Field '{field}' validation: {df[field].notnull().sum()} valid, {df[field].isnull().sum()} invalid")

    df['valid'] &= df['payee_country'].apply(lambda x: validate_iso_code(x, valid_iso_codes))
    df['valid'] &= df['payee_due_date'].apply(lambda x: validate_date(x))
    df['valid'] &= df['payee_phone_number'].apply(lambda x: validate_phone_number(x))
    df['valid'] &= df['currency'].apply(lambda x: validate_currency_code(x))
    df['valid'] &= df['due_amount'].apply(lambda x: isinstance(x, (int, float)))

    invalid_rows = df[~df['valid']]
    if not invalid_rows.empty:
        print("Invalid rows detected:")
        print(invalid_rows)

    valid_data = df[df['valid']].drop(columns=['valid']).to_dict('records')

    if not valid_data:
        print("No valid records found during validation.")

    return valid_data


def save_to_mongo(data):
    print("Saving data to MongoDB...") 
    try:
        client = MongoClient(mongo_uri)
        db = client['pay-managing']
        collection = db['payment_records']
        result = collection.insert_many(data)
        print(f"{len(result.inserted_ids)} records inserted into MongoDB.")
    except Exception as e:
        print(f"Error while inserting data to MongoDB: {e}")

file_path = "upload/payment_information.csv"
valid_records = normalize_and_validate_csv(file_path)

if valid_records:
    save_to_mongo(valid_records)
else:
    print("No valid records to save.")