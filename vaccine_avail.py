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
from geo_dist import GeoLocation


@cachetools.func.ttl_cache(maxsize=100, ttl=30 * 60)
@retry(KeyError, tries=5, delay=2)
def get_data(URL):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' +
               'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93' +
               'Safari/537.36 Edg/90.0.818.51'}
    response = requests.get(URL, headers=headers, timeout=3)
    if response.status_code != 200:
        return (False, response.status_code)
    # print(response.text)
    data = json.loads(response.text)['centers']
    return (True, data)


def get_availability_by_dist(days: int, district_ids: List[int],
                             min_age_limit: int, current_lat=0,
                             current_long=0, geolocation_filter=False,
                             max_dist=10):
    base = datetime.datetime.today()
    date_list = [base + datetime.timedelta(days=x) for x in range(days)]
    date_str = [x.strftime("%d-%m-%Y") for x in date_list]
    gl = GeoLocation(current_lat, current_long)

    all_date_df = None
    error_str = ''

    for date_s in date_str:
        for district_id in district_ids:
            print(f"checking for INP_DATE:{date_s} & DIST_ID:{district_id}")
            URL = ("https://cdn-api.co-vin.in/api/v2/appointment/sessions/" +
                   "public/calendarByDistrict?district_id={}&date={}".format(
                       district_id, date_s))
            ret, data = get_data(URL)
            if not ret:
                print(data)
                error = ("Recd err %s from cowin site for URL %s" % (
                    data, URL))
                error_str += error + '\n'
                continue
            df = pd.DataFrame(data)
            if len(df):
                df = df.explode("sessions")
                df['min_age_limit'] = df.sessions.apply(
                    lambda x: x['min_age_limit'])
                df['available_capacity'] = df.sessions.apply(
                    lambda x: x['available_capacity'])
                df['date'] = df.sessions.apply(lambda x: x['date'])
                df['vaccine'] = df.sessions.apply(lambda x: x['vaccine'])
                df = df[["date", "min_age_limit", "available_capacity",
                         "pincode", "name", "state_name", "district_name",
                         "block_name", "fee_type", "vaccine", "lat", "long"]]
                if all_date_df is not None:
                    all_date_df = pd.concat([all_date_df, df])
                else:
                    all_date_df = df

    if len(all_date_df):
        all_date_df = all_date_df.drop(["block_name"], axis=1).sort_values(
            ["date", "min_age_limit", "district_name", "available_capacity"],
            ascending=[True, True, True, False])
        all_date_df = all_date_df[all_date_df.min_age_limit <= min_age_limit]
        all_date_df = all_date_df[all_date_df.available_capacity > 0]
        if geolocation_filter:
            all_date_df["dist"] = all_date_df.apply(
                lambda x: gl.calculate_dist(
                    x["lat"], x["long"], max_dist), axis=1)
            all_date_df = all_date_df[all_date_df["dist"]]

        return True, all_date_df
    return False, error_str


def get_availability_by_pincode(days: int, pincodes: List[int],
                                min_age_limit: int):
    base = datetime.datetime.today()
    date_list = [base + datetime.timedelta(days=x) for x in range(days)]
    date_str = [x.strftime("%d-%m-%Y") for x in date_list]

    all_date_df = None

    for date_s in date_str:
        for pincode in pincodes:
            print(f"checking for INP_DATE:{date_s} & pincode:{pincode}")
            URL = ("https://cdn-api.co-vin.in/api/v2/appointment/sessions/" +
                   "public/calendarByPin?pincode={}&date={}".format(
                       pincode, date_s))
            ret, data = get_data(URL)
            if not ret:
                error = ("Received err %s while fetching data from" +
                         "co-win site" % data)
                return False, error
            df = pd.DataFrame(data)
            if len(df):
                df = df.explode("sessions")
                df['min_age_limit'] = df.sessions.apply(
                    lambda x: x['min_age_limit'])
                df['available_capacity'] = df.sessions.apply(
                    lambda x: x['available_capacity'])
                df['date'] = df.sessions.apply(lambda x: x['date'])
                df['vaccine'] = df.sessions.apply(lambda x: x['vaccine'])
                df = df[["date", "min_age_limit", "available_capacity",
                         "pincode", "name", "state_name", "district_name",
                         "block_name", "fee_type", "vaccine"]]
                if all_date_df is not None:
                    all_date_df = pd.concat([all_date_df, df])
                else:
                    all_date_df = df

        if not all_date_df.empty:
            all_date_df = all_date_df.drop(["block_name"], axis=1).sort_values(
                ["date", "min_age_limit", "district_name",
                 "available_capacity"], ascending=[True, True, True, False])
            all_date_df = all_date_df[all_date_df.min_age_limit <=
                                      min_age_limit]
            all_date_df = all_date_df[all_date_df.available_capacity > 0]
            if not all_date_df.empty:
                return all_date_df
    return True, pd.DataFrame()


def send_email(data_frame, age, receiver_email):
    # Used most of code from https://realpython.com/python-send-email/ and
    # modified
    if data_frame is None or len(data_frame.index) == 0:
        print("Empty Data")
        return

    sender_email = os.environ['SENDER_EMAIL']
    # receiver_email = os.environ['RECEIVER_EMAIL']
    message = MIMEMultipart("alternative")
    message["Subject"] = "Availability for Max Age {} Count {}".format(
        age, len(data_frame.index))
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
    message["Subject"] = ("Test Email from Robot finding available slot for" +
                          "vaccine for 18+")
    message["From"] = sender_email
    message["To"] = receiver_email

    text = """\
    Hi,
    I will email you availability of vaccine slots for 18+ once it is
     uploaded on cowin app"""

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


def send_error_email(error_msg, receiver_email):
    sender_email = os.environ['SENDER_EMAIL']

    message = MIMEMultipart("alternative")
    message["Subject"] = ("Error received running script to find" +
                          "vaccine for 18+")
    message["From"] = sender_email
    message["To"] = receiver_email

    text = """\
    Hi,
    Please find the error from the script """

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

    html = "{}{}{}".format(html_header, error_msg, html_footer)

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
    Bangalore_Urban = 265
    BBMP = 294
    dist_ids = [BBMP, Bangalore_Rural, Bangalore_Urban]
    pincodes = [560076, 560078]
    next_n_days = 10
    min_age_limit = 18
    # coord's of our house (J P nagar bangalore)
    current_lat = float(os.environ["CURRENT_LAT"])
    current_long = float(os.environ["CURRENT_LONG"])

    """
    ret, availability_data = get_availability_by_pincode(next_n_days, pincodes,
                                                         min_age_limit)
    """
    try:
        ret, availability_data = get_availability_by_dist(
            next_n_days, dist_ids, min_age_limit,
            current_lat=current_lat,
            current_long=current_long,
            geolocation_filter=True,
            max_dist=100)

        if not ret:
            # email errors
            send_error_email(availability_data, "deepacks@gmail.com")
            exit()
        print(availability_data)
        send_email(availability_data, min_age_limit, "deepacks@gmail.com")
        send_email(availability_data, min_age_limit, "sarahagrawal@gmail.com")
    except Exception as e:
        print("Received exception %s \n" % e)
        send_error_email(e, "deepacks@gmail.com")

    # send_email(availability_data, min_age_limit, "riteshnytime@gmail.com")
    if len(sys.argv) > 1:
        if sys.argv[1] == "test_email":
            send_test_email("deepacks@gmail.com")
            send_test_email("riteshnytime@gmail.com")
