import requests
import datetime
import shelve
import time
import random
import os
from dotenv import load_dotenv
from loguru import logger

logger.add("bbsittor.log", rotation="500 MB")
load_dotenv()


TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')

COOKIES = {
    'session': os.getenv('BB_SESSION'),
}

HEADERS = {
    'Host': 'api.bbst.eu',
    'accept': '*/*',
    'accept-language': 'en-GB,en;q=0.9',
    'x-api-version': '1.0.0',
    'user-agent': 'BabySittor/401 CFNetwork/1399 Darwin/22.1.0',
    'x-app-build': '401',
    'x-device-id': '1200609',
    'x-app-version': '4.5.7',
    'x-platform': 'ios',
}


def random_sleep(unit: str = 's', min: int = 1, max: int = 5):
    t = random.randint(min, max)
    if unit == 's':
        logger.info(f'Sleeping for {t} seconds.')
    elif unit == 'm':
        t = t * 60
        logger.info(f'Sleeping for {t//60} minutes.')
    elif unit == 'h':
        t = t * 60 * 60
        logger.info(f'Sleeping for {t//3600} hours.')
    else:
        raise ValueError('Unexpected unit.')
    time.sleep(t)


def send_message(message: str):
    url = f'https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage'

    data = {
        'chat_id': TG_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown',
    }

    response = requests.post(url, data=data)
    response.raise_for_status()


def fetch_bbsittings(start_date: str = None):
    if start_date is None:
        start_date = datetime.datetime.now()
        start_date = start_date.replace(
            hour=0, minute=0, second=0, microsecond=0)
        start_date = start_date.isoformat(sep=' ')

    url = f'https://api.bbst.eu/home/babysitter/without_favorite?categories=one_time,recurrent,long_time,tutoring&expand=applications[0],children,babysitting_affinity_for_control_panel,is_me_in_smart_alert,parent,start_address,week_days,number_of_days_to_pay,next_local_start_time,is_hidden,payment_intents.last_payment_error_code&last_day={start_date}&limit=7&limit_score=5&sorting=local'

    response = requests.get(url, headers=HEADERS, cookies=COOKIES)
    response.raise_for_status()
    return response.json()


def parse_bbsitting(bb):
    assert bb['price_unit'] == 'per_hour', 'Unexpected price unit.'

    category_by_id = {
        1: '👶🏻 Babysitting',
        2: '🔁 Régulier',
        3: '🏖 Vacances',
        4: '📚 Cours',
    }
    week_days_by_number = {
        0: 'L',
        1: 'Ma',
        2: 'Me',
        3: 'J',
        4: 'V',
        5: 'S',
        6: 'D',
    }

    id = bb['id']
    start = datetime.datetime.fromisoformat(bb['local_start_time'])
    end = datetime.datetime.fromisoformat(bb['local_end_time'])
    description = bb['description']
    price = bb['price'] / 100  # in euro
    category_id = bb['category_id']
    # in km
    distance = bb['babysitting_affinity_for_control_panel']['distance_to_start'] / 1000
    postal_code = bb['start_address']['postal_code']
    city = bb['start_address']['city']
    address_url = bb['start_address']['google_url']
    week_days_number = [day['local_number'] for day in bb['week_days']['data']]

    category = category_by_id[category_id]
    week_days = [week_days_by_number[number] for number in week_days_number]

    if (start - end).days == 0:
        msg_date = f'le {start.strftime("%d/%m")} de {start.strftime("%H:%M")} à {end.strftime("%H:%M")}'
    else:
        msg_date = f'du {start.strftime("%d/%m")} au {end.strftime("%d/%m")} ({"|".join(week_days)})'

    msg = f'''{category} {price}€|h {msg_date} à {distance:.1f}km ([{city} {postal_code}]({address_url}))

    {description.strip() if description else 'Pas de description.'}

👍🏻 /like{id}        👎🏻 /dislike{id}
    '''

    return msg


def fetch_new_bbsittings(delta_days: int = 7):
    end_date = datetime.datetime.now() + datetime.timedelta(days=delta_days)

    last_date = None
    db = shelve.open('bbsittings.db')

    while last_date is None or last_date < end_date:
        need_sleep = False
        bb_lists = fetch_bbsittings(last_date)
        for bb_data in bb_lists:
            if bb_data['object'] != 'babysitting_day':
                logger.warning('Unexpected object "{type}" data={data}',
                               type=bb_data['object'],
                               data=bb_data)
                continue

            for bb in bb_data['babysittings']['data']:
                id = str(bb['id'])
                if id in db:
                    continue

                try:
                    msg = parse_bbsitting(bb)
                    send_message(msg)
                    db[id] = bb
                    logger.info('Found new babysitting. data={data}', data=bb)
                except Exception as e:
                    logger.error(
                        'Error while parsing babysitting {id} ({e}) data={data}', id=id, e=e, data=bb)
                finally:
                    raise SystemExit
                    need_sleep = True

        last_date = datetime.datetime.fromisoformat(bb_data['day'])

        if need_sleep:
            random_sleep(unit='s', min=1, max=10)


if __name__ == '__main__':
    fetch_new_bbsittings()
    # send_message('👍🏻 /jaime\n👎🏻 /jaimepas\n🤷🏻‍♂️ /peutetre\n👀 /voir\n👋🏻 /stop')
