# Download the helper library from https://www.twilio.com/docs/python/install
import os
from twilio.rest import Client


# Find your Account SID and Auth Token at twilio.com/console
# and set the environment variables. See http://twil.io/secure
account_sid = os.environ['TWILIO_ACCOUNT_SID']
auth_token = os.environ['TWILIO_AUTH_TOKEN']
client = Client(account_sid, auth_token)
to_numbers = ['+919880899884', '+919886266679']

for to_number in to_numbers:
    message = client.messages \
                    .create(
                        body="Hello I am going to send you sms once vaccine is"
                        "available",
                        from_='+17656133255',
                        to=to_number
                    )

print(message.sid)

