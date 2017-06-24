from datetime import datetime
from json import dumps, loads
from pprint import pprint
from re import compile
from sys import argv
from urllib import urlencode
from urlparse import parse_qs, urlparse

from autobahn.twisted.websocket import connectWS, WebSocketClientFactory, WebSocketClientProtocol
from autobahn.websocket.compress import (
    PerMessageDeflateOffer,
    PerMessageDeflateResponse,
    PerMessageDeflateResponseAccept,
)
from requests import Session
from twisted.internet import reactor
from twisted.internet.protocol import ReconnectingClientFactory

DATES_PATTERN = compile(r'platformConfig = (\{.*?\});')
MATCHES_PATTERN = compile(
    r'data-eventId="(\d+?)".*?class="home-team-name"\s*title="(.*?)".*?class="away-team-name"\s*title="(.*?)"'
)
URL_1_PATTERN = compile(r'LV.setFrameSrc\(\'(.*?)\'\)')
URL_2_PATTERN = compile(r'<iframe.*?src="(.*?)".*?>')
HOSTNAME_PATTERN = compile(r'window.socketServerURL = "https://(.*?)";')
TOKEN_PATTERN = compile(r'window.validationToken = "(.*?)";')
TOPIC_PATTERN = compile(r'window.matchId = "(.*?)";')


class WebSocketsClient(object):

    def __init__(self, url, topic):
        self._url = url
        self._topic = topic
        self._factory = self._build_factory()
        self._connection = None

    def _build_factory(self):
        factory = WebSocketsFactory(self._url)
        factory.protocol = WebSocketsProtocol
        factory.topic = self._topic

        factory.setProtocolOptions(perMessageCompressionAccept=self._accept)
        factory.setProtocolOptions(perMessageCompressionOffers=[self._build_offer()])

        return factory

    def _accept(self, response):
        if isinstance(response, PerMessageDeflateResponse):
            return PerMessageDeflateResponseAccept(response)

    def _build_offer(self):
        return PerMessageDeflateOffer(
            accept_max_window_bits=True,
            accept_no_context_takeover=False,
            request_max_window_bits=0,
            request_no_context_takeover=False,
        )

    def connect(self):
        print('connect()')
        reactor.callFromThread(connectWS, self._factory)

    def disconnect(self):
        print('disconnect()')
        self._factory.doStop()


class WebSocketsFactory(WebSocketClientFactory, ReconnectingClientFactory):

    def clientConnectionFailed(self, connector, reason):
        self.retry(connector)

    def clientConnectionLost(self, connector, reason):
        self.retry(connector)


class WebSocketsProtocol(WebSocketClientProtocol):

    def onOpen(self):
        print('onOpen()')

    def onClose(self, was_clean, code, reason):
        print('onClose()')
        print('was clean:', repr(was_clean))
        print('code:', repr(code))
        print('reason:', repr(reason))

    def onMessage(self, payload, isBinary):
        print('onMessage()')
        prefix, message = self.parse(payload)
        print(prefix)
        if prefix == '0':
            return
        if prefix == '3':
            return
        if prefix == '40':
            message = [
                'subscribe',
                {
                    'Topic': self.factory.topic,
                    'ConditionsUpdates':'true',
                    'LiveUpdates':'true',
                    'OddsUpdates':'true',
                    'VideoUpdates':'true',
                },
            ]
            message = dumps(message)
            message = '{prefix:d}{message:s}'.format(prefix=42, message=message)
            self.sendMessage(message)
            return
        if prefix == '42':
            print(message[1].keys())
            message = '2'
            self.sendMessage(message)
            return

    def sendMessage(self, payload, *args, **kwargs):
        print(payload)
        super(WebSocketsProtocol, self).sendMessage(payload, *args, **kwargs)

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
        if message:
            message = loads(message)
        return prefix, message


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
    web_sockets_client = WebSocketsClient(url, topic)
    web_sockets_client.connect()
    reactor.run()


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
