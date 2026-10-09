"""Split-session parsing, backwards compatibility and publication failure protection."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import export_program as exporter
from validate_public import validate_file

HEADER = '**Время работы секции (с перерывами)**'


def record(other='', start='12:30', end='17:00'):
    values = {'id': 'section-test', 'title': 'Тестовая секция', 'date': '2026-11-14',
              'status': 'Опубликовано', 'topic': 'Экономика и бизнес', 'format': 'Секция',
              'attendance': 'Онлайн', 'other': other,
              'startsAt': f'2026-11-14T{start}:00+05:00' if start else None,
              'endsAt': f'2026-11-14T{end}:00+05:00' if end else None}
    return {'id': 'rec-test', 'fields': {exporter.FIELDS[k]: v for k, v in values.items()}}


def build(**kwargs):
    snapshot = exporter.build_snapshot([record(**kwargs)], [])
    exporter.validate_snapshot(snapshot)
    return snapshot


class SectionIntervals(unittest.TestCase):
    def test_split_schedule_preserves_break_and_description(self):
        text = 'Описание\n\n' + HEADER + '\n12:30–14:30\n15:00–17:00\n\n**Контакты 2026**\nКонтакт уточняется'
        event = build(other=text)['events'][0]
        self.assertEqual(event['content']['other'], text)
        self.assertEqual([(i['start'], i['end']) for i in event['intervals']],
                         [('12:30', '14:30'), ('15:00', '17:00')])
        self.assertEqual(event['intervals'][1]['startsAt'], '2026-11-14T15:00:00+05:00')
        self.assertEqual((event['start'], event['end']), ('12:30', '17:00'))

    def test_three_intervals_bullets_spaces_and_dashes(self):
        text = '### Время работы секции (с перерывами):\r\n- 9:00 - 10:00\r\n\r\n• 10:30 — 12:00\r\n3. **13:00–15:00**'
        event = build(other=text, start='09:00', end='15:00')['events'][0]
        self.assertEqual(len(event['intervals']), 3)
        self.assertEqual(event['intervals'][0]['start'], '09:00')

    def test_separate_prose_with_digits_can_follow(self):
        text = HEADER+'\n12:30–14:30\n15:00–17:00\n\nВсе время по Екатеринбургу, UTC+5.'
        self.assertEqual(len(build(other=text)['events'][0]['intervals']), 2)

    def test_times_outside_named_block_are_not_interpreted(self):
        event = build(other='Для справки: 12:30–14:30\n**Продолжение секции**\n15:00–17:00')['events'][0]
        self.assertEqual(event['intervals'], [])

    def test_block_can_supply_missing_overall_times(self):
        event = build(other=HEADER+'\n12:30–14:30\n15:00–17:00', start=None, end=None)['events'][0]
        self.assertEqual((event['start'], event['end']), ('12:30', '17:00'))

    def test_rejects_incorrect_or_overlapping_intervals(self):
        invalid = ['12:30–14:30\n15:00–1700', '12:30–14:30\n15.00–17.00',
                   '12:30–14:30\n14:00–17:00', '15:00–17:00\n12:30–14:30',
                   '12:30–12:30', '25:00–26:00', '12:30–14:30\n\n15:00–1700',
                   '12:30–14:30\n**15.00–1700**', '']
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(ValueError):
                build(other=HEADER+'\n'+body)

    def test_overall_times_must_match_all_intervals(self):
        for start, end in [('12:00', '17:00'), ('12:30', '14:30')]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                build(other=HEADER+'\n12:30–14:30\n15:00–17:00', start=start, end=end)

    def test_duplicate_schedule_blocks_are_rejected(self):
        with self.assertRaises(ValueError):
            build(other=HEADER+'\n12:30–14:30\n'+HEADER+'\n15:00–17:00')

    def test_older_last_good_snapshot_still_validates(self):
        snapshot = build()
        del snapshot['events'][0]['intervals']
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'program.json'
            path.write_text(json.dumps(snapshot))
            self.assertEqual(validate_file(path)['recordCount'], 1)

    def test_modified_wire_intervals_are_rejected(self):
        snapshot = build(other=HEADER+'\n12:30–14:30\n15:00–17:00')
        for replacement in ({'start': '15:00', 'end': '17:00', 'startsAt': '2026-11-13T15:00:00+05:00', 'endsAt': '2026-11-14T17:00:00+05:00'},
                            {'start': '14:00', 'end': '17:00', 'startsAt': '2026-11-14T14:00:00+05:00', 'endsAt': '2026-11-14T17:00:00+05:00'}):
            changed = deepcopy(snapshot)
            changed['events'][0]['intervals'][1] = replacement
            with self.assertRaises(ValueError):
                exporter.validate_snapshot(changed)

    def test_invalid_snapshot_leaves_both_public_files_unchanged(self):
        snapshot = build(other=HEADER+'\n12:30–14:30\n15:00–17:00')
        with tempfile.TemporaryDirectory() as folder:
            exporter.write_snapshot(snapshot, folder)
            paths = [Path(folder) / filename for filename in ('program.json', 'program.last-good.json')]
            previous = [p.read_bytes() for p in paths]
            broken = deepcopy(snapshot)
            broken['events'][0]['intervals'][1]['start'] = '14:00'
            with self.assertRaises(ValueError):
                exporter.write_snapshot(broken, folder)
            self.assertEqual([p.read_bytes() for p in paths], previous)


if __name__ == '__main__':
    unittest.main()
