from datetime import datetime
from json import dumps, loads
from logging import basicConfig, INFO, getLogger
from pprint import pprint
from re import compile
from ssl import CERT_NONE
from sys import argv
from urllib import urlencode
from urlparse import parse_qs, urlparse

from requests import Session
from websocket import WebSocketApp

DATES_PATTERN = compile(r'platformConfig = (\{.*?\});')
MATCHES_PATTERN = compile(
    r'data-eventId="(\d+?)".*?class="home-team-name"\s*title="(.*?)".*?class="away-team-name"\s*title="(.*?)"'
)
URL_1_PATTERN = compile(r'LV.setFrameSrc\(\'(.*?)\'\)')
URL_2_PATTERN = compile(r'<iframe.*?src="(.*?)".*?>')
HOSTNAME_PATTERN = compile(r'window.socketServerURL = "https://(.*?)";')
TOKEN_PATTERN = compile(r'window.validationToken = "(.*?)";')
TOPIC_PATTERN = compile(r'window.matchId = "(.*?)";')

basicConfig()

logger = getLogger('websocket')
logger.setLevel(INFO)


class WebSockets(object):

    def __init__(self, url, topic):
        self.url = url
        self.topic = topic
        self.connection = None

    def connect(self):
        logger.debug('connect()')
        self.connection = WebSocketApp(
            self.url,
            on_open=self.on_open,
            on_close=self.on_close,
            on_message=self.on_message,
            on_error=self.on_error,
        )
        sslopt = {
            'cert_reqs': CERT_NONE,
        }
        self.connection.run_forever(sslopt=sslopt)

    def disconnect(self):
        logger.debug('disconnect()')
        if self.connection:
            self.connection.close()

    def send(self, payload, *args, **kwargs):
        logger.debug(payload)
        self.connection.send(payload)

    def on_open(self, _):
        logger.debug('on_open()')
        pass

    def on_close(self, _):
        logger.debug('on_close()')
        pass

    def on_message(self, _, payload):
        logger.debug('on_message()')
        prefix, message = self.parse(payload)
        if prefix == '0':
            return
        if prefix == '3':
            return
        if prefix == '40':
            message = [
                'subscribe',
                {
                    'Topic': self.topic,
                    'ConditionsUpdates': 'true',
                    'LiveUpdates': 'true',
                    'OddsUpdates': 'false',
                    'VideoUpdates': 'false',
                },
            ]
            message = dumps(message)
            message = '{prefix:d}{message:s}'.format(prefix=42, message=message)
            self.send(message)
            return
        if prefix == '42':
            message = loads(message)
            if 'ActiveMQMessage' in message[1]:
                message[1]['ActiveMQMessage'] = loads(message[1]['ActiveMQMessage'])
                mlu = message[1]['ActiveMQMessage']['MLU']
                t = mlu.get('T', [])
                eid = mlu.get('EID', '?')
                en = mlu.get('EN', '?')
                logger.info((mlu['CPT'], mlu['CR'], mlu['PSID'], mlu['TSID'], mlu['SCH'], mlu['SCA'], len(t), eid, en))
            message = '2'
            self.send(message)
            return

    def parse(self, payload):
        prefix = []
        message = payload
        while True:
            if not message:
                break
            character = message[0]
            if not character.isdigit():
                break
            prefix.append(character)
            message = message[1:]
        prefix = ''.join(prefix)
        return prefix, message

    def on_error(self, _, error):
        logger.debug('on_error()')
        logger.debug(error)
        pass


def main(options):
    if options[1] == '--matches':
        execute_matches()
        return
    if options[1] == '--web-sockets':
        execute_web_sockets(argv[2])
        return


def execute_matches():
    session = Session()
    url = 'https://www.betfair.com/sport/football'
    method = 'GET'
    response = session.request(url=url, method=method)
    contents = response.text
    contents = contents.replace('\n', '')
    dates = get_dates(contents)
    matches = get_matches(contents, dates)
    pprint(matches)


def get_matches(contents, dates):
    matches = []
    items = MATCHES_PATTERN.findall(contents)
    for item in items:
        id = item[0]
        id = int(id)
        home = item[1]
        away = item[2]
        date = dates[id]
        match = {
            'id': id,
            'teams': {
                'home': home,
                'away': away,
            },
            'date': date,
        }
        matches.append(match)
    return matches


def get_dates(contents):
    item = DATES_PATTERN.search(contents)
    if not item:
        return
    contents = item.group(1)
    json = loads(contents)
    instructions = json['page']['config']['instructions']
    dates = {}
    for instruction in instructions:
        if instruction['type'] == 'eventupdates':
            arguments = instruction['arguments']
            for argument in arguments:
                start_time = argument['startTime']
                start_time = start_time / 1000
                start_time = int(start_time)
                start_time = datetime.utcfromtimestamp(start_time)
                dates[argument['eventId']] = start_time
    return dates


def execute_web_sockets(event_id):
    session = Session()
    url = get_web_sockets_url_1(session, event_id)
    url = get_web_sockets_url_2(session, url)
    url, topic = get_web_sockets_url_and_topic(session, url)
    web_sockets = WebSockets(url, topic)
    web_sockets.connect()


def get_web_sockets_url_1(session, event_id):
    url = 'https://videoplayer.betfair.com/GetPlayer.do'
    method = 'GET'
    params = {
        'allowPopup': 'true',
        'contentOnly': 'true',
        'contentType': 'viz',
        'contentView': 'viz',
        'eID': event_id,
        'height': '214',
        'tr': '2',
        'width': '374',
    }
    response = session.request(url=url, method=method, params=params)
    contents = response.text
    contents = contents.replace('\n', '')
    match = URL_1_PATTERN.search(contents)
    if not match:
        print('Invalid URL - #1')
        exit()
    url = match.group(1)
    return url


def get_web_sockets_url_2(session, url):
    method = 'GET'
    response = session.request(url=url, method=method)
    contents = response.text
    contents = contents.replace('\n', '')
    match = URL_2_PATTERN.search(contents)
    if not match:
        print('Invalid URL - #2')
        exit()
    url = match.group(1)
    return url


def get_web_sockets_url_and_topic(session, url):
    method = 'GET'
    response = session.request(url=url, method=method)
    contents = response.text
    contents = contents.replace('\n', '')
    match = HOSTNAME_PATTERN.search(contents)
    if not match:
        print('Invalid Hostname')
        exit()
    hostname = match.group(1)
    match = TOKEN_PATTERN.search(contents)
    if not match:
        print('Invalid Token')
        exit()
    token = match.group(1)
    wt = get_wt(url)
    params = {
        'cssdiff': 'https%3A%2F%2Fassets.cdnbf.net%2Fstatic%2Fdatavis%2Fbf-css%2Fbetfair1.css',
        'defaultview': 'viz',
        'EIO': '3',
        'flash': 'n',
        'height': '438',
        'lang': 'en',
        'multimatch': 'false',
        'partnerId': '7',
        'referer': 'https%3A%2F%2Fwab-visualisation.performgroup.com%2Fcsb%2Findex.html%3FwbuserId',
        'statsswitch': 'false',
        'streamonly': 'true',
        'token': token,
        'topreferer': 'wab-visualisation.performgroup.com',
        'transport': 'websocket',
        'version': '1.31',
        'width': '600',
        'wt': wt,
    }
    params = urlencode(params)
    url = 'wss://{hostname:s}/socket.io/?{params:s}'.format(hostname=hostname, params=params)
    match = TOPIC_PATTERN.search(contents)
    if not match:
        print('Invalid Match ID')
        exit()
    topic = match.group(1)
    return url, topic


def get_wt(url):
    url = urlparse(url)
    query = parse_qs(url.query)
    wt = query['wt']
    return wt


if __name__ == '__main__':
    main(argv)
