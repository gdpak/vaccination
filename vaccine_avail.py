import datetime
import json
import os
import smtplib
import ssl
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

import cachetools.func
import pandas as pd
import requests
from retry import retry


def get_all_district_ids():
    district_df_all = None
    for state_code in range(1, 40):
        response = requests.get("https://cdn-api.co-vin.in/api/v2/admin/location/districts/{}".format(state_code), timeout=3)
        district_df = pd.DataFrame(json.loads(response.text))
        district_df = pd.json_normalize(district_df['districts'])
        if district_df_all is None:
            district_df_all = district_df
        else:
            district_df_all = pd.concat([district_df_all, district_df])

        district_df_all.district_id = district_df_all.district_id.astype(int)

    district_df_all = district_df_all[["district_name", "district_id"]].sort_values("district_name")
    return district_df_all

@cachetools.func.ttl_cache(maxsize=100, ttl=30 * 60)
@retry(KeyError, tries=5, delay=2)
def get_data(URL):
    response = requests.get(URL, timeout=3)
    data = json.loads(response.text)['centers']
    return data

def get_availability(days: int, district_ids: List[int], min_age_limit: int):
    base = datetime.datetime.today()
    date_list = [base + datetime.timedelta(days=x) for x in range(days)]
    date_str = [x.strftime("%d-%m-%Y") for x in date_list]
    INP_DATE = date_str[-1]

    all_date_df = None

    for district_id in district_ids:
        print(f"checking for INP_DATE:{INP_DATE} & DIST_ID:{district_id}")
        URL = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/calendarByDistrict?district_id={}&date={}".format(district_id, INP_DATE)
        data = get_data(URL)
        #print (data)
        df = pd.DataFrame(data)
        print ("df = ", df)
        if len(df):
            df = df.explode("sessions")
            df['min_age_limit'] = df.sessions.apply(lambda x: x['min_age_limit'])
            df['available_capacity'] = df.sessions.apply(lambda x: x['available_capacity'])
            df['date'] = df.sessions.apply(lambda x: x['date'])
            df['vaccine'] = df.sessions.apply(lambda x:x['vaccine'])
            df = df[["date", "min_age_limit", "available_capacity", "pincode", "name", "state_name", "district_name", "block_name", "fee_type", "vaccine"]]
            if all_date_df is not None:
                all_date_df = pd.concat([all_date_df, df])
            else:
                all_date_df = df

    if all_date_df is not None:
        all_date_df = all_date_df.drop(["block_name"], axis=1).sort_values(["date", "min_age_limit", "district_name", "available_capacity"], ascending=[True, True, True, False])
        all_date_df = all_date_df[all_date_df.min_age_limit <= min_age_limit]
        all_date_df = all_date_df[all_date_df.available_capacity>0]
        return all_date_df
    return pd.DataFrame()

def get_availability_by_pincode(days: int, pincodes: List[int], min_age_limit: int):
    base = datetime.datetime.today()
    date_list = [base + datetime.timedelta(days=x) for x in range(days)]
    date_str = [x.strftime("%d-%m-%Y") for x in date_list]
    INP_DATE = date_str[-1]
    print (date_str)

    all_date_df = None

    for date_s in date_str:
        for pincode in pincodes:
            print(f"checking for INP_DATE:{date_s} & pincode:{pincode}")
            print('https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/calendarByPin?pincode=560076&date=06-05-2021')
            URL = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/calendarByPin?pincode={}&date={}".format(pincode, date_s)
            print (URL)
            data = get_data(URL)
            print (data)
            df = pd.DataFrame(data)
            if len(df):
                df = df.explode("sessions")
                df['min_age_limit'] = df.sessions.apply(lambda x: x['min_age_limit'])
                df['available_capacity'] = df.sessions.apply(lambda x: x['available_capacity'])
                df['date'] = df.sessions.apply(lambda x: x['date'])
                df['vaccine'] = df.sessions.apply(lambda x:x['vaccine'])
                df = df[["date", "min_age_limit", "available_capacity", "pincode", "name", "state_name", "district_name", "block_name", "fee_type", "vaccine"]]
                if all_date_df is not None:
                    all_date_df = pd.concat([all_date_df, df])
                else:
                    all_date_df = df

        if not all_date_df.empty:
            all_date_df = all_date_df.drop(["block_name"], axis=1).sort_values(["date", "min_age_limit", "district_name", "available_capacity"], ascending=[True, True, True, False])
            all_date_df = all_date_df[all_date_df.min_age_limit <= min_age_limit]
            all_date_df = all_date_df[all_date_df.available_capacity>0]
            if not all_date_df.empty:
                return all_date_df
    return pd.DataFrame()


def send_email(data_frame, age, receiver_email):
    # Used most of code from https://realpython.com/python-send-email/ and modified
    if data_frame is None or len(data_frame.index) == 0:
        print("Empty Data")
        return

    sender_email = os.environ['SENDER_EMAIL']
    #receiver_email = os.environ['RECEIVER_EMAIL']

    message = MIMEMultipart("alternative")
    message["Subject"] = "Availability for Max Age {} Count {}".format(age, len(data_frame.index))
    message["From"] = sender_email
    message["To"] = receiver_email

    text = """\
    Hi,
    Please refer vaccine availability"""

    html_header = """\
    <html>
      <body>
        <p>
    """

    html_footer = """\

        </p>
      </body>
    </html>
    """

    html = "{}{}{}".format(html_header, data_frame.to_html(), html_footer)

    part1 = MIMEText(text, "plain")
    part2 = MIMEText(html, "html")

    message.attach(part1)
    message.attach(part2)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender_email, os.environ['SENDER_PASSWORD'])
        server.sendmail(
            sender_email, receiver_email, message.as_string()
        )

def send_test_email(receiver_email):
    sender_email = os.environ['SENDER_EMAIL']

    message = MIMEMultipart("alternative")
    message["Subject"] = "Test Email from Robot finding available slot for vaccine for 18+"
    message["From"] = sender_email
    message["To"] = receiver_email

    text = """\
    Hi,
    I will email you availability of vaccine slots for 18+ once it is uploaded on cowin app"""

    html_header = """\
    <html>
      <body>
        <p>
    """

    html_footer = """\

        </p>
      </body>
    </html>
    """

    html = "{}{}".format(html_header, html_footer)

    part1 = MIMEText(text, "plain")
    part2 = MIMEText(html, "html")

    message.attach(part1)
    message.attach(part2)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender_email, os.environ['SENDER_PASSWORD'])
        server.sendmail(
            sender_email, receiver_email, message.as_string()
            )

if __name__ == "__main__":
    Bangalore_Rural = 276
    Bangalore_Urban = 256
    dist_ids = [Bangalore_Rural, Bangalore_Urban]
    pincodes = [560076, 560078]
    next_n_days = 20
    min_age_limit = 18

    #availability_data = get_availability(next_n_days, dist_ids, min_age_limit)
    availability_data = get_availability_by_pincode(next_n_days, pincodes, min_age_limit)
    print (availability_data)
    #if not availability_data.empty:
    send_email(availability_data, min_age_limit, "deepacks@gmail.com")
    send_email(availability_data, min_age_limit, "sarahagrawal@gmail.com")
    send_email(availability_data, min_age_limit, "riteshnytime@gmail.com")

    if len(sys.argv) > 1:
        if sys.argv[1] == "test_email":
            send_test_email("deepacks@gmail.com")
            send_test_email("riteshnytime@gmail.com")
