from datetime import datetime
from json import loads
from pprint import pprint
from re import compile
from sys import argv

from autobahn.twisted.websocket import connectWS, WebSocketClientFactory, WebSocketClientProtocol
from autobahn.websocket.compress import (
    PerMessageDeflateOffer,
    PerMessageDeflateResponse,
    PerMessageDeflateResponseAccept,
)
from requests import Session
from twisted.internet import reactor
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.python import log
from txaio import start_logging, use_twisted

DATES_PATTERN = compile(r'platformConfig = (\{.*?\});')
MATCH_PATTERN = compile(
    r'data-eventId="(\d+?)".*?class="home-team-name"\s*title="(.*?)".*?class="away-team-name"\s*title="(.*?)"'
)

use_twisted()

start_logging(level='debug')


class Factory(WebSocketClientFactory, ReconnectingClientFactory):

    def clientConnectionFailed(self, connector, reason):
        self.retry(connector)

    def clientConnectionLost(self, connector, reason):
        self.retry(connector)


class Protocol(WebSocketClientProtocol):

    def onConnect(self, response):
        message = 'onConnect: {peer:s}'.format(peer=response.peer)
        log.debug(message)

    def onOpen(self):
        log.debug('onOpen')
        # while True:
        #     self.sendMessage(u"Hello, world!".encode('utf8'))
        #     self.sendMessage(b"\x00\x01\x03\x04", isBinary=True)
        #     yield sleep(1)

    def onMessage(self, payload, isBinary):
        message = 'onMessage: isBinary = {is_binary:s}'.format(is_binary=isBinary)
        log.debug(message)
        log.debug(payload)

    def onClose(self, wasClean, code, reason):
        log.debug('onClose')
        message = 'Was Clean?: {was_clean:s}'.format(was_clean=wasClean)
        log.debug(message)
        message = 'Code      : {code:s}'.format(code=code)
        log.debug(message)
        message = 'Reason    : {reason:s}'.format(reason=reason)
        log.debug(message)


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
    items = MATCH_PATTERN.findall(contents)
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
    reactor.run()

    url = 'wss://ec2-54-194-233-78.performgroup.com/socket.io/?token=ab4ca9729c312877e835f861e74b3c7ddc3a735fd5fc791764ff1bc798e3c2375bf837f213aeeefa55398b1fe8e1c20ee3d04a076fcad87a47ef38eec3f8a0be0f65082274658ca1c581dda8e78a2017bad77e02a15a6e044f10540737f3bcded6f01acf8d704c12dc0759e8a4c970b4&referer=https%3A%2F%2Fwab-visualisation.performgroup.com%2Fcsb%2Findex.html%3FwbuserId&wt=eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJ3YWJhcGkiLCJhdWQiOiJjc2IiLCJpYXQiOjE0OTc3NzgzNTEsImV4cCI6MTQ5Nzc3ODM3MSwidXVpZCI6ImRrZm0wZWRzMWtqZzBsb2t5YjNla2VjNHAiLCJ1c2VyaWQiOiIwIiwiY3VzdG9tZXJpZCI6IjcifQ.j3fq3fIk351JL2Y9al5sRG7hot_V0us4f5sdHyioQsM&width=374&height=214&cssdiff=https%3A%2F%2Fassets.cdnbf.net%2Fstatic%2Fdatavis%2Fbf-css%2Fbetfair1.css&flash=y&streamonly=true&partnerId=7&statsswitch=false&lang=en&defaultview=viz&version=1.31&topreferer=secure.betfair.premiumtv.co.uk&multimatch=false&EIO=3&transport=websocket'
    factory = Factory(url)
    factory.protocol = Protocol
    factory.setProtocolOptions(perMessageCompressionAccept=accept)
    offer = get_offer()
    offers = [offer]
    factory.setProtocolOptions(perMessageCompressionOffers=offers)
    reactor.callFromThread(connectWS, factory)


def accept(response):
    if isinstance(response, PerMessageDeflateResponse):
        return PerMessageDeflateResponseAccept(response)


def get_offer():
    return PerMessageDeflateOffer(
        accept_max_window_bits=True,
        accept_no_context_takeover=False,
        request_max_window_bits=0,
        request_no_context_takeover=False,
    )


if __name__ == '__main__':
    main(argv)
