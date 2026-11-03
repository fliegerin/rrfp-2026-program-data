from copy import deepcopy
import unittest
from test_section_intervals import record, exporter
from test_speaker_order import person

class EventRoles(unittest.TestCase):
    def test_roles_belong_to_event_and_ignore_global_role(self):
        people=[person('t','Ирина Тургель','Тургель','Модератор'),person('r','Людмила Ружанская','Ружанская','Модератор'),person('s','Анастасия Судакова','Судакова','Модератор'),person('c','Ольга Чернова','Чернова','Модератор'),person('d','Дмитрий Толмачев','Толмачев')]
        a,b=record(),record()
        a['fields'][exporter.FIELDS['id']]='china-symposium';b['fields'][exporter.FIELDS['id']]='creative-hr'
        a['fields'][exporter.FIELDS['speakers']]=[p['id'] for p in people]
        a['fields'][exporter.FIELDS['moderators']]=['d','d'];b['fields'][exporter.FIELDS['moderators']]=['t']
        before=deepcopy((people,a,b));out=exporter.build_snapshot([a,b],people);exporter.validate_snapshot(out)
        es={e['id']:e for e in out['events']}
        self.assertEqual(es['china-symposium']['moderators'],['Дмитрий Толмачев']);self.assertEqual(es['china-symposium']['leaders'],[])
        self.assertTrue(all(p['role']=='Спикер' for p in es['china-symposium']['speakerDetails']))
        self.assertEqual(es['creative-hr']['moderators'],['Ирина Тургель']);self.assertEqual(es['creative-hr']['speakers'],[])
        self.assertEqual((people,a,b),before)
        for p in people:p['fields'][exporter.SPEAKER_FIELDS['role']]='Спикер'
        self.assertEqual(out['events'],exporter.build_snapshot([a,b],people)['events'])

    def test_three_explicit_roles_can_coexist_without_duplicate_links(self):
        e=record();people=[person('p','Анна Петрова','Петрова','Модератор')]
        for k in ['speakers','moderators','leaders']:e['fields'][exporter.FIELDS[k]]=['p','p']
        out=exporter.build_snapshot([e],people);exporter.validate_snapshot(out);x=out['events'][0]
        for k,role in [('speakerDetails','Спикер'),('moderatorDetails','Модератор'),('leaderDetails','Руководитель')]:
            self.assertEqual(len(x[k]),1);self.assertEqual(x[k][0]['role'],role)

    def test_missing_moderator_refuses_incomplete_export(self):
        e=record();e['fields'][exporter.FIELDS['moderators']]=['missing']
        with self.assertRaisesRegex(ValueError,'unresolved moderator link'):exporter.build_snapshot([e],[])

    def test_invalid_public_role_refuses_publication(self):
        e=record();e['fields'][exporter.FIELDS['moderators']]=['p']
        out=exporter.build_snapshot([e],[person('p','Ирина Тургель')]);out['events'][0]['moderatorDetails'][0]['role']='Спикер'
        with self.assertRaises(ValueError):exporter.validate_snapshot(out)
