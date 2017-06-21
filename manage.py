from datetime import datetime
from json import loads
from pprint import pprint
from re import compile
from sys import argv

from requests import Session

DATES_PATTERN = compile(r'platformConfig = (\{.*?\});')
MATCH_PATTERN = compile(
    r'data-eventId="(\d+?)".*?class="home-team-name"\s*title="(.*?)".*?class="away-team-name"\s*title="(.*?)"'
)


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
    pass


if __name__ == '__main__':
    main(argv)
