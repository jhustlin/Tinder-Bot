import time

from twilio.rest import TwilioRestClient


ACCOUNT_SID = 'ACbbc1ca1314db9cae20f3c488dec14c7a'
AUTH_TOKEN = '983782249529ec6e36fbb39f007d999d'
COUNTRIES = ['FI', 'PL', 'GA']


def get_messages(number):
    client = TwilioRestClient(ACCOUNT_SID, AUTH_TOKEN)
    messages = client.messages.list(to=number)
    return messages[0].body if any(messages) else None


def search_for_numbers(client):
    for code in COUNTRIES:
        numbers = client.phone_numbers.search(country=code, type='mobile', sms_enabled=True)
        for number in [number for number in numbers if number.capabilities['SMS']]:
            return number
    return None


def purchase_number():
    client = TwilioRestClient(ACCOUNT_SID, AUTH_TOKEN)
    number = search_for_numbers(client)
    if number is not None:
        client.phone_numbers.purchase(phone_number=number.phone_number,
                                      sms_url='http://twimlets.com/echo?Twiml=%3CResponse%3E%3C%2FResponse%3E')
        LAST_PURCHASE = time.time()
    return number.phone_number


if __name__ == '__main__':
    print purchase_number()
