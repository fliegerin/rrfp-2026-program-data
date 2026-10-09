#!/usr/bin/env python3
"""RRFP snapshot exporter. Python 3.9+, no packages; credentials only in environment."""
import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE = 'apptKG7eM1lbiQoo2'
TABLES = {'events': 'tblZKYFewA9dC0B7X', 'speakers': 'tblE4u9BARSOee4XT'}
TZ = ZoneInfo('Asia/Yekaterinburg')
FIELDS = {
    'id': 'fldtW5hMR75PGLmdp', 'title': 'fldqqId8g0YMSSgXl',
    'translation': 'fldPiPCK84icQQaNy', 'date': 'fldshtuDMXQdh7kTQ',
    'startsAt': 'fld6irbz8QbsIujZD', 'endsAt': 'fldBdPRzwR2Xh9u5u',
    'topic': 'fldRx0Y7LoPKoPlOo', 'format': 'fldk8778WxkJOkpOX',
    'attendance': 'fld9qVu7RISV0xXF7', 'venue': 'fldNL7SWWuDxrDJUw',
    'room': 'fldAfDCZFe1E4WVJf', 'code': 'fldeotq9IRLAdtk2w',
    'partner': 'fldQ82nPmNspA0CEX', 'speakers': 'fldfbwHvFd89LwpLx',
    'language': 'fldU6K1X0AeipkGZi', 'interpretation': 'fldjv0A5rHRagqfoQ',
    'invitationOnly': 'flduBzY5dL9OQA9OW', 'separateRegistration': 'fldevGxf4eiKdsdYM',
    'registrationUrl': 'fldHeHiHGrhwaEhvu', 'onlineUrl': 'fldybAOJ3l4JwmREy',
    'status': 'fldTDSuaZjCPDYqCj', 'updatedAt': 'fldUH4o9rZ1LSmqPE',
    'intro': 'flddC3yWtvEtE18js', 'agenda': 'fld1qKTV2wsP9Ax8A',
    'formatResult': 'fldcUBVWxlIhiup9m', 'audience': 'fldpCm7vf77tKwaGY',
    'other': 'fldJNIxKjM1CUM5JL',
}
SPEAKER_FIELDS = {'name': 'fldhcc2gNElwvOOOb', 'position': 'fldEBD7hccsQzYRGx',
                  'organization': 'fldEWdOmzLYElZ7oc', 'role': 'fldjIOyhIgduHk8n2'}
TOPICS = {'Устойчивое развитие': 'esg', 'Экономика и бизнес': 'econ',
          'Технологии и данные': 'tech', 'Образование и люди': 'people',
          'Территории и города': 'city', 'Общая программа': 'general'}
CONTENT_KEYS = ('intro', 'agenda', 'formatResult', 'audience', 'other')
TIME_PATTERN = r'(?:[01]?\d|2[0-3]):[0-5]\d'
INTERVAL_PATTERN = re.compile(rf'({TIME_PATTERN})\s*[-–—−‑]\s*({TIME_PATTERN})')


def heading_text(line):
    return re.sub(r'\s+', ' ', re.sub(r'[#*_]', '', line)).strip().rstrip(':').casefold()


def parse_section_intervals(other, date, start, end, ident):
    """Read only the named schedule block; preserve all description text unchanged."""
    lines = other.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    headings = [i for i, line in enumerate(lines) if heading_text(line) in (
        'время работы секции', 'время работы секции (с перерывами)')]
    if not headings:
        return []
    if len(headings) != 1:
        raise ValueError(f'{ident}: duplicate section schedule headings')
    intervals, separated = [], False
    for raw in lines[headings[0] + 1:]:
        line = raw.strip()
        if not line:
            separated = True
            continue
        # The next Markdown heading ends the block; bold time rows remain valid.
        if re.match(r'^#{1,6}\s+', line) or (re.fullmatch(r'\*\*[^*]+\*\*', line) and not re.match(r'^\*\*\s*\d', line)):
            break
        line = re.sub(r'^(?:[-*+•]\s+|\d+[.)]\s+)', '', line).strip().strip('*_')
        match = INTERVAL_PATTERN.fullmatch(line)
        if not match:
            # A separate prose paragraph can follow; a mistyped time must not be skipped.
            if intervals and separated and not re.match(r'\d', line):
                break
            raise ValueError(f'{ident}: invalid schedule row; use HH:MM–HH:MM')
        separated = False
        first, last = [t.zfill(5) for t in match.groups()]
        if last <= first or (intervals and first < intervals[-1]['end']):
            raise ValueError(f'{ident}: schedule intervals overlap, are out of order or end before they start')
        begin = datetime.fromisoformat(f'{date}T{first}:00').replace(tzinfo=TZ)
        finish = datetime.fromisoformat(f'{date}T{last}:00').replace(tzinfo=TZ)
        intervals.append({'start': first, 'end': last,
                          'startsAt': begin.isoformat(), 'endsAt': finish.isoformat()})
    if not intervals:
        raise ValueError(f'{ident}: section schedule heading has no intervals')
    if start and start != timestamp(intervals[0]['startsAt']):
        raise ValueError(f'{ident}: Начало must match the first section interval')
    if end and end != timestamp(intervals[-1]['endsAt']):
        raise ValueError(f'{ident}: Окончание must match the last section interval')
    return intervals


def validate_intervals(event):
    """The optional field keeps older last-good snapshots compatible."""
    intervals = event.get('intervals', [])
    if not isinstance(intervals, list):
        raise ValueError('Invalid section intervals')
    previous_end = None
    for item in intervals:
        if not isinstance(item, dict) or any(
            not isinstance(item.get(k), str) or not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', item[k])
            for k in ('start', 'end')
        ):
            raise ValueError('Invalid section interval time')
        if item['end'] <= item['start'] or (previous_end and item['start'] < previous_end):
            raise ValueError('Invalid section interval order')
        for key, clock in (('startsAt', 'start'), ('endsAt', 'end')):
            dt = timestamp(item.get(key))
            if not dt or dt.date().isoformat() != event['date'] or dt.strftime('%H:%M') != item[clock] or dt.second or dt.microsecond:
                raise ValueError('Section interval date/time does not match')
        previous_end = item['end']
    if intervals and any(event.get(key) != intervals[index][key]
                         for key, index in (('start', 0), ('end', -1), ('startsAt', 0), ('endsAt', -1))):
        raise ValueError('Section intervals do not match the overall event range')


def scalar(value):
    if value is None:
        return ''
    if isinstance(value, dict):
        value = value.get('name', '')
    if not isinstance(value, str):
        raise ValueError('Expected a text/select value')
    return value.strip()


def cells(record):
    return record.get('cellValuesByFieldId', record.get('fields', {}))


def safe_url(value):
    value = scalar(value)
    if not value:
        return ''
    parts = urlsplit(value)
    if parts.scheme not in ('https', 'http') or not parts.netloc or parts.username or parts.password:
        raise ValueError('A link must be an absolute HTTP(S) URL without credentials')
    return value


def timestamp(value):
    value = scalar(value)
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Date/time must include a timezone')
    return dt.astimezone(TZ)


def build_snapshot(event_records, speaker_records, mode='published'):
    people = {}
    for record in speaker_records:
        values = cells(record)
        person = {'id': record['id'], **{k: scalar(values.get(v)) for k, v in SPEAKER_FIELDS.items()}}
        people[record['id']] = person
    events, ids = [], set()
    for record in event_records:
        values = cells(record)
        f = {k: values.get(v) for k, v in FIELDS.items()}
        status = scalar(f['status'])
        if status not in ('Черновик', 'Опубликовано', 'Скрыто'):
            raise ValueError('Unknown/missing publication status')
        if status == 'Скрыто' or (mode == 'published' and status != 'Опубликовано'):
            continue
        ident, title = scalar(f['id']), scalar(f['title'])
        if not re.fullmatch(r'[A-Za-z0-9_-]+', ident) or ident in ids or not title:
            raise ValueError('Missing/duplicate/unsafe Event ID or empty title')
        ids.add(ident)
        start, end = timestamp(f['startsAt']), timestamp(f['endsAt'])
        if end and not start:
            raise ValueError(f'{ident}: end without start')
        if start and end and end <= start:
            raise ValueError(f'{ident}: end must follow start')
        date = scalar(f['date']) or (start.date().isoformat() if start else '')
        # The preserved UI is explicitly for 11–14 November 2026.
        if date not in ('2026-11-11', '2026-11-12', '2026-11-13', '2026-11-14'):
            raise ValueError(f'{ident}: date outside RRFP 2026 programme')
        if start and start.date().isoformat() != date:
            raise ValueError(f'{ident}: date and start disagree in UTC+5')
        if end and end.date().isoformat() != date:
            raise ValueError(f'{ident}: overnight events require a UI schema change')
        topic = TOPICS.get(scalar(f['topic']))
        kind, attendance = scalar(f['format']), scalar(f['attendance'])
        if not topic or not kind or attendance not in ('Очно', 'Онлайн', 'Очно и онлайн'):
            raise ValueError(f'{ident}: missing/unknown topic, event type or attendance')
        linked = []
        for link in f['speakers'] or []:
            pid = link if isinstance(link, str) else link['id']
            if pid not in people or not people[pid]['name']:
                raise ValueError(f'{ident}: unresolved speaker link')
            linked.append(people[pid])
        venue, room = scalar(f['venue']), scalar(f['room'])
        place = ' · '.join(x for x in (venue, 'ауд. ' + room if room else '') if x)
        place = place or ('Онлайн' if attendance == 'Онлайн' else 'Место уточняется')
        content = {k: scalar(f[k]) for k in CONTENT_KEYS}
        intervals = parse_section_intervals(content['other'], date, start, end, ident)
        if intervals:
            start, end = timestamp(intervals[0]['startsAt']), timestamp(intervals[-1]['endsAt'])
        # Summary uses the first prose paragraph; no Airtable field names become headings.
        prose = [p for p in re.split(r'\n\s*\n', content['intro']) if p and not re.fullmatch(r'\*\*[^\n]+\*\*', p)]
        summary = re.sub(r'[*_#`]', '', prose[0]).replace('\n', ' ') if prose else ''
        if len(summary) > 240:
            summary = summary[:237].rsplit(' ', 1)[0] + '…'
        online = safe_url(f['onlineUrl'])
        event = {
            'id': ident, 'title': title, 'translation': scalar(f['translation']),
            'date': date, 'day': int(date[-2:]), 'start': start.strftime('%H:%M') if start else None,
            'end': end.strftime('%H:%M') if end else None,
            'startsAt': start.isoformat() if start else None, 'endsAt': end.isoformat() if end else None,
            'intervals': intervals,
            'datePending': False, 'topic': topic, 'format': kind, 'attendance': attendance,
            'venue': venue, 'room': room, 'place': place, 'code': scalar(f['code']),
            'partners': [scalar(f['partner'])] if scalar(f['partner']) else [],
            'speakers': [p['name'] for p in linked if p['role'] != 'Модератор'],
            'speakerDetails': linked, 'leaders': [p['name'] for p in linked if p['role'] == 'Модератор'],
            'summary': summary, 'content': content, 'language': scalar(f['language']),
            'interpretation': scalar(f['interpretation']), 'invitationOnly': f['invitationOnly'] is True,
            'separateRegistration': f['separateRegistration'] is True,
            'registrationUrl': safe_url(f['registrationUrl']), 'onlineUrl': online,
            'canJoin': bool(online and attendance in ('Онлайн', 'Очно и онлайн')),
            'feature': ident in ('econ-plenary', 'education-plenary', 'esg'),
            'updatedAt': scalar(f['updatedAt']),
        }
        events.append(event)
    events.sort(key=lambda e: (e['date'], e['start'] or '99:99', e['id']))
    return {'schemaVersion': 1, 'generatedAt': datetime.now(timezone.utc).isoformat(),
            'timezone': 'Asia/Yekaterinburg', 'mode': mode, 'recordCount': len(events), 'events': events}


def validate_snapshot(snapshot, allow_empty=False):
    if snapshot.get('schemaVersion') != 1 or snapshot.get('timezone') != 'Asia/Yekaterinburg':
        raise ValueError('Unsupported snapshot version/timezone')
    if snapshot.get('mode') not in ('preview', 'published'):
        raise ValueError('Unsupported snapshot mode')
    events = snapshot.get('events')
    if not isinstance(events, list) or len(events) != snapshot.get('recordCount'):
        raise ValueError('Incomplete snapshot')
    if not events and not allow_empty:
        raise ValueError('Empty export refused; last successful snapshot remains unchanged')
    ids = set()
    for e in events:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', e['id']) or e['id'] in ids:
            raise ValueError('Invalid/duplicate event ID')
        ids.add(e['id'])
        if not e['title'] or e['topic'] not in TOPICS.values() or not e['format']:
            raise ValueError('Invalid event')
        if e['date'] != f"2026-11-{e['day']:02d}" or e['day'] not in (11, 12, 13, 14):
            raise ValueError('Invalid event date')
        for key in ('registrationUrl', 'onlineUrl'):
            safe_url(e[key])
        validate_intervals(e)


def bridge_html(snapshot):
    # textarea is inert and survives Bitrix's script relocation. Escape closing tags and all HTML.
    data = html.escape(json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')), quote=False)
    return '<!-- Generated snapshot; no executable code and no credentials. -->\n' + \
           '<textarea id="rrfp-program-snapshot" hidden aria-hidden="true">' + data + '</textarea>\n'


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o644)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_snapshot(snapshot, output_dir, allow_empty=False):
    validate_snapshot(snapshot, allow_empty)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    current = output_dir / 'program.json'
    previous = snapshot
    if current.exists():
        try:
            candidate = json.loads(current.read_text())
            validate_snapshot(candidate, allow_empty)
            if candidate['mode'] != snapshot['mode']:
                raise ValueError('Preview/published outputs must use different directories')
            previous = candidate
        except (json.JSONDecodeError, KeyError):
            # A malformed current file must never become the fallback.
            fallback = output_dir / 'program.last-good.json'
            if fallback.exists():
                previous = json.loads(fallback.read_text())
                validate_snapshot(previous, allow_empty)
    # The current JSON is promoted last. All data is fetched and validated before any write.
    atomic_write(output_dir / 'program.last-good.json', json.dumps(previous, ensure_ascii=False, indent=2) + '\n')
    atomic_write(output_dir / 'bitrix-data-last-good.html', bridge_html(previous))
    atomic_write(output_dir / 'bitrix-data.html', bridge_html(snapshot))
    atomic_write(current, json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')


def request_json(url, token):
    for attempt in range(4):
        try:
            request = Request(url, headers={'Authorization': 'Bearer ' + token})
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                # Never include exception URL/body: may contain credentials in other integrations.
                raise RuntimeError(f'Airtable HTTP {error.code}') from None
            time.sleep(30 if error.code == 429 else 2 ** attempt)


def fetch_records(table, fields, token):
    records, offset, offsets = [], None, set()
    while True:
        query = [('pageSize', '100'), ('returnFieldsByFieldId', 'true')]
        query.extend(('fields[]', value) for value in fields)
        if offset:
            query.append(('offset', offset))
        result = request_json(f'https://api.airtable.com/v0/{BASE}/{table}?' + urlencode(query), token)
        if not isinstance(result.get('records'), list):
            raise ValueError('Airtable returned an incomplete response')
        records.extend(result['records'])
        offset = result.get('offset')
        if not offset:
            return records
        if offset in offsets:
            raise ValueError('Repeated pagination offset')
        offsets.add(offset)
        time.sleep(.25)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('preview', 'published'), default='published')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--input', help='Offline connector export for initial generation/testing')
    parser.add_argument('--allow-empty', action='store_true', help='Explicitly publish an empty programme')
    args = parser.parse_args()
    try:
        if args.input:
            raw = json.loads(Path(args.input).read_text())
            for key in ('events', 'speakers'):
                if raw[key].get('nextCursor'):
                    raise ValueError('Offline export is only the first page')
                total = raw[key].get('metadata', {}).get('totalRecordCount')
                if total is not None and total != len(raw[key]['records']):
                    raise ValueError('Offline export is incomplete')
            events, speakers = raw['events']['records'], raw['speakers']['records']
        else:
            token = os.environ.get('AIRTABLE_TOKEN')
            if not token:
                raise ValueError('Set AIRTABLE_TOKEN in the private runner environment')
            events = fetch_records(TABLES['events'], FIELDS.values(), token)
            time.sleep(.25)
            speakers = fetch_records(TABLES['speakers'], SPEAKER_FIELDS.values(), token)
        snapshot = build_snapshot(events, speakers, args.mode)
        write_snapshot(snapshot, args.output_dir, args.allow_empty)
        print(f"Generated {snapshot['recordCount']} events ({args.mode}); snapshot validated.")
    except Exception as error:
        print('Export failed; current snapshot was not promoted. ' + str(error), file=__import__('sys').stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
