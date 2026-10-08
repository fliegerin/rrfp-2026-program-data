"""Refresh public JSON; Airtable credentials exist only in the runner environment."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

import export_program as exporter
from validate_public import validate_file

PUBLIC = Path(__file__).resolve().parents[1] / 'public'


def refresh():
    token = os.environ.get('AIRTABLE_TOKEN')
    if not token:
        raise ValueError('Missing AIRTABLE_TOKEN repository secret')
    # Fetch and validate everything before touching the existing public files.
    events = exporter.fetch_records(exporter.TABLES['events'], exporter.FIELDS.values(), token)
    time.sleep(.25)
    speakers = exporter.fetch_records(exporter.TABLES['speakers'], exporter.SPEAKER_FIELDS.values(), token)
    snapshot = exporter.build_snapshot(events, speakers, 'published')
    exporter.validate_snapshot(snapshot)
    with tempfile.TemporaryDirectory() as folder:
        staging = Path(folder)
        for filename in ('program.json', 'program.last-good.json'):
            source = PUBLIC / filename
            if source.exists():
                validate_file(source)
                shutil.copyfile(source, staging / filename)
        exporter.write_snapshot(snapshot, staging)
        for filename in ('program.json', 'program.last-good.json'):
            validate_file(staging / filename)
        # Both files are deployed together by Pages only after all steps succeed.
        for filename in ('program.last-good.json', 'program.json'):
            exporter.atomic_write(PUBLIC / filename, (staging / filename).read_text(encoding='utf-8'))
    print(f'Validated {snapshot["recordCount"]} published events. No credentials in public files.')


if __name__ == '__main__':
    try:
        refresh()
    except Exception as error:
        # Avoid logging arbitrary API payloads or URLs containing credentials.
        print(f'Update failed ({type(error).__name__}); previous deployment remains available.', file=sys.stderr)
        sys.exit(1)
