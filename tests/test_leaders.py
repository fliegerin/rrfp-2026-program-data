"""Event-specific section leaders must reach the public snapshot."""
from copy import deepcopy
import unittest

from test_section_intervals import record, exporter
from test_speaker_order import person


class EventLeaders(unittest.TestCase):
    def build(self, event, people):
        snapshot = exporter.build_snapshot([event], people)
        exporter.validate_snapshot(snapshot)
        return snapshot['events'][0]

    def test_explicit_links_export_without_speakers_or_global_moderator_role(self):
        people = [person('rec1', 'Тамара Владимировна Куприна', 'Куприна'),
                  person('rec2', 'Елена Борисовна Бедрина', 'Бедрина')]
        event = record()
        event['fields'][exporter.FIELDS['leaders']] = [
            {'id': p['id'], 'name': p['fields'][exporter.SPEAKER_FIELDS['name']]} for p in people]
        before = deepcopy((event, people))
        result = self.build(event, people)
        self.assertEqual(result['leaders'], ['Елена Борисовна Бедрина', 'Тамара Владимировна Куприна'])
        self.assertEqual(result['speakers'], [])
        self.assertEqual(result['speakerDetails'], [])
        self.assertEqual((event, people), before)

    def test_rest_links_merge_legacy_moderators_without_duplicates(self):
        people = [person('rec1', 'Жанна Сергеевна Беляева', 'Беляева', 'Модератор'),
                  person('rec2', 'Александр Александрович Ишуков', 'Ишуков')]
        event = record()
        event['fields'][exporter.FIELDS['leaders']] = ['rec2', 'rec1', 'rec2']
        event['fields'][exporter.FIELDS['speakers']] = ['rec1']
        self.assertEqual(self.build(event, people)['leaders'],
                         ['Жанна Сергеевна Беляева', 'Александр Александрович Ишуков'])

    def test_leadership_does_not_spread_to_other_events(self):
        leader = person('rec1', 'Наталья Рэмовна Кельчевская', 'Кельчевская')
        first, second = record(), record()
        second['fields'][exporter.FIELDS['id']] = 'another-section'
        first['fields'][exporter.FIELDS['leaders']] = ['rec1']
        second['fields'][exporter.FIELDS['speakers']] = ['rec1']
        events = {e['id']: e for e in exporter.build_snapshot([first, second], [leader])['events']}
        self.assertEqual(events['section-test']['leaders'], [leader['fields'][exporter.SPEAKER_FIELDS['name']]])
        self.assertEqual(events['another-section']['leaders'], [])
        self.assertEqual(events['another-section']['speakers'], [leader['fields'][exporter.SPEAKER_FIELDS['name']]])

    def test_unresolved_or_unnamed_leader_refuses_incomplete_export(self):
        for people in ([], [person('missing', '')]):
            with self.subTest(people=people):
                event = record()
                event['fields'][exporter.FIELDS['leaders']] = ['missing']
                with self.assertRaisesRegex(ValueError, 'unresolved leader link'):
                    self.build(event, people)

    def test_empty_leader_field_keeps_old_snapshot_contract(self):
        self.assertEqual(self.build(record(), [])['leaders'], [])

    def test_explicit_event_leader_does_not_promote_moderators_of_other_events(self):
        people = [person('rec1', 'Людмила Станиславовна Ружанская', 'Ружанская', 'Модератор'),
                  person('rec2', 'Дмитрий Евгеньевич Толмачев', 'Толмачев', 'Модератор')]
        event = record()
        event['fields'][exporter.FIELDS['speakers']] = ['rec1', 'rec2']
        event['fields'][exporter.FIELDS['leaders']] = ['rec2']
        before = deepcopy((event, people))
        result = self.build(event, people)
        self.assertEqual(result['leaders'], ['Дмитрий Евгеньевич Толмачев'])
        self.assertEqual(result['speakers'], ['Людмила Станиславовна Ружанская'])
        self.assertEqual([p['role'] for p in result['speakerDetails']], ['Спикер', 'Модератор'])
        self.assertEqual((event, people), before)

    def test_legacy_moderator_without_explicit_event_leaders_still_exports(self):
        moderator = person('rec1', 'Олег Буклемишев', 'Буклемишев', 'Модератор')
        event = record()
        event['fields'][exporter.FIELDS['speakers']] = ['rec1']
        self.assertEqual(self.build(event, [moderator])['leaders'], ['Олег Буклемишев'])


if __name__ == '__main__':
    unittest.main()
