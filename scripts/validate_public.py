"""Validate both browser snapshots before any deployment (stdlib only)."""
from datetime import datetime
import json
from pathlib import Path
import re
import export_program as exporter

PUBLIC = Path(__file__).resolve().parents[1] / 'public'
TEXT_KEYS = ('title', 'translation', 'format', 'attendance', 'place', 'venue', 'room',
             'code', 'summary', 'language', 'interpretation', 'onlineUrl', 'registrationUrl', 'updatedAt')
BOOL_KEYS = ('invitationOnly', 'separateRegistration', 'feature', 'datePending', 'canJoin')


def validate_file(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    exporter.validate_snapshot(data)
    if data['mode'] != 'published':
        raise ValueError('Only published snapshots may be deployed')
    if datetime.fromisoformat(data['generatedAt'].replace('Z', '+00:00')).tzinfo is None:
        raise ValueError('Snapshot timestamp must include timezone')
    for e in data['events']:
        if any(not isinstance(e.get(k), str) for k in TEXT_KEYS):
            raise ValueError('Missing text field')
        if any(type(e.get(k)) is not bool for k in BOOL_KEYS):
            raise ValueError('Missing boolean field')
        if e['attendance'] not in ('Очно', 'Онлайн', 'Очно и онлайн'):
            raise ValueError('Invalid attendance')
        for k in ('start', 'end'):
            if k not in e or (e[k] is not None and not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', e[k])):
                raise ValueError('Invalid time')
        if e['end'] and (not e['start'] or e['end'] <= e['start']):
            raise ValueError('Invalid interval')
        for k in ('speakers', 'leaders', 'partners'):
            if not isinstance(e.get(k), list) or any(not isinstance(s, str) for s in e[k]):
                raise ValueError('Invalid text list')
        if not isinstance(e.get('content'), dict) or any(not isinstance(e['content'].get(k), str) for k in exporter.CONTENT_KEYS):
            raise ValueError('Missing content')
        if not isinstance(e.get('speakerDetails'), list):
            raise ValueError('Missing speakers')
        for person in e['speakerDetails']:
            if any(not isinstance(person.get(k), str) for k in ('id', 'name', 'position', 'organization', 'role')):
                raise ValueError('Invalid speaker')
    return data


if __name__ == '__main__':
    for filename in ('program.json', 'program.last-good.json'):
        data = validate_file(PUBLIC / filename)
        print(f'{filename}: {data["recordCount"]} published events validated.')
