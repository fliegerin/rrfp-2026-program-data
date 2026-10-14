"""New Airtable records get stable IDs without changing existing programme IDs."""
from copy import deepcopy
import unittest

from test_section_intervals import record, exporter


class EventIds(unittest.TestCase):
    def test_missing_id_uses_record_id_and_survives_title_or_order_changes(self):
        first = record()
        first['id'] = 'recNhe6eP3ok7jWgJ'
        first['fields'].pop(exporter.FIELDS['id'])
        second = record()
        second['id'] = 'recpTfQhjNC63lVdF'
        second['fields'][exporter.FIELDS['id']] = '   '
        before = deepcopy([first, second])
        snapshot = exporter.build_snapshot([first, second], [])
        exporter.validate_snapshot(snapshot)
        self.assertEqual({e['id'] for e in snapshot['events']}, {first['id'], second['id']})
        first['fields'][exporter.FIELDS['title']] = 'Новое название'
        revised = exporter.build_snapshot([second, first], [])
        self.assertEqual({e['id'] for e in revised['events']}, {first['id'], second['id']})
        self.assertEqual(before[0]['fields'].get(exporter.FIELDS['id']), None)
        self.assertNotIn(exporter.FIELDS['id'], first['fields'])

    def test_existing_explicit_ids_are_preserved(self):
        self.assertEqual(exporter.build_snapshot([record()], [])['events'][0]['id'], 'section-test')

    def test_invalid_or_duplicate_ids_are_still_rejected(self):
        first, second = record(), record()
        with self.assertRaises(ValueError):
            exporter.build_snapshot([first, second], [])
        first['fields'][exporter.FIELDS['id']] = 'unsafe/id'
        with self.assertRaises(ValueError):
            exporter.build_snapshot([first], [])
        first['fields'].pop(exporter.FIELDS['id'])
        first['id'] = 'section-test'
        with self.assertRaises(ValueError):
            exporter.build_snapshot([first, second], [])

    def test_missing_title_and_inconsistent_dates_still_rejected(self):
        event = record()
        event['fields'].pop(exporter.FIELDS['id'])
        event['fields'][exporter.FIELDS['title']] = ''
        with self.assertRaises(ValueError):
            exporter.build_snapshot([event], [])
        event['fields'][exporter.FIELDS['title']] = 'Мероприятие'
        event['fields'][exporter.FIELDS['date']] = '2026-11-13'
        with self.assertRaisesRegex(ValueError, 'date and start disagree'):
            exporter.build_snapshot([event], [])


if __name__ == '__main__':
    unittest.main()
