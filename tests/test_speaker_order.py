"""The programme must sort participants by surname without changing their data."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import export_program as exporter
from test_section_intervals import record


def person(ident, name, surname=None, role='Спикер'):
    fields = {exporter.SPEAKER_FIELDS[key]: value for key, value in
              {'name': name, 'position': 'Должность ' + ident,
               'organization': 'Организация ' + ident, 'role': role}.items()}
    if surname is not None:
        fields[exporter.SPEAKER_SORT_FIELD] = surname
    return {'id': ident, 'fields': fields}


class SpeakerOrder(unittest.TestCase):
    def event(self, people):
        event = record()
        event['fields'][exporter.FIELDS['speakers']] = [p['id'] for p in people]
        snapshot = exporter.build_snapshot([event], people)
        exporter.validate_snapshot(snapshot)
        return snapshot['events'][0]

    def test_surname_order_keeps_positions_and_role_groups(self):
        people = [person('rec1', 'Алексей Овакимян', 'Овакимян'),
                  person('rec2', 'Сергей Афонцев', 'Афонцев'),
                  person('rec3', 'Дмитрий Мраморов', 'Мраморов'),
                  person('rec4', 'Олег Буклемишев', 'Буклемишев', 'Модератор')]
        before = deepcopy(people)
        result = self.event(people)
        self.assertEqual(result['speakers'], ['Сергей Афонцев', 'Дмитрий Мраморов', 'Алексей Овакимян'])
        self.assertEqual(result['leaders'], ['Олег Буклемишев'])
        self.assertEqual([p['id'] for p in result['speakerDetails']], ['rec2', 'rec4', 'rec3', 'rec1'])
        for p in result['speakerDetails']:
            self.assertEqual(p['position'], 'Должность ' + p['id'])
            self.assertEqual(p['organization'], 'Организация ' + p['id'])
            self.assertEqual(set(p), {'id', 'name', 'position', 'organization', 'role'})
        self.assertEqual(people, before)

    def test_saved_export_fallback_and_yo_follow_russian_order(self):
        result = self.event([person('rec1', 'Анна Жукова'),
                             person('rec2', 'Пётр Ёлкин'),
                             person('rec3', 'Юлия Александровна Долгих'),
                             person('rec4', 'Вера Елкина')])
        self.assertEqual(result['speakers'], ['Юлия Александровна Долгих', 'Пётр Ёлкин',
                                             'Вера Елкина', 'Анна Жукова'])


if __name__ == '__main__':
    unittest.main()
