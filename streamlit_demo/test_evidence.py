"""Regression tests for provenance, ambiguity, and safe HTML rendering."""
import unittest
from evidence import select_evidence, highlighted_context
from qa_client import QAClient, QAError


class EvidenceTests(unittest.TestCase):
    def test_single_value_requires_matching_section(self):
        question = 'What is the patient allergic to?'
        answer = 'The patient is allergic to penicillin.'
        result = select_evidence('ALLERGIES:\nPenicillin.', question, answer)
        self.assertEqual(result['evidence_text'], 'Penicillin.')
        for note in ['MEDICATIONS:\nPenicillin.', 'ALLERGIES:\nNo penicillin.',
                     'ALLERGIES:\nPenicillin was prescribed.', 'ALLERGIES:\nAspirin.']:
            self.assertFalse(select_evidence(note, question, answer)['evidence_matches'])

    def test_planned_care_requires_matching_modality(self):
        note = 'PLAN:\nThe patient will be treated with I-125 seed implantation.'
        answer = 'The patient will be treated with I-125 seed implantation.'
        self.assertTrue(select_evidence(note, 'What treatment is planned?', answer)['evidence_matches'])
        self.assertFalse(select_evidence(note, 'What treatment was performed?', answer)['evidence_matches'])
        self.assertFalse(select_evidence(note, 'What treatment is planned?',
                                        answer.replace('will', 'might'))['evidence_matches'])
        self.assertFalse(select_evidence(note, 'What treatment is planned?',
                                        answer.replace('will be', 'was'))['evidence_matches'])

    def test_complete_reason_and_truncated_word(self):
        from pathlib import Path
        note = (Path(__file__).resolve().parents[1] / 'mt_onc_50/mt_oncology_25.txt').read_text()
        question = 'Why is the patient not a candidate for chlorambucil or radioactive phosphorus?'
        answer = ('The patient is not a candidate for chlorambucil or radioactive phosphorus '
                  'because of his young age and the concern for secondary malignancy.')
        result = select_evidence(note, question, answer)
        self.assertTrue(result['evidence_matches'])
        for match in result['evidence_matches']:
            self.assertIn('secondary malignancy', match['evidence_text'])
            self.assertEqual(note[match['evidence_start']:match['evidence_end']], match['evidence_text'])
        self.assertIn('secondary malignancy', highlighted_context(note, result))
        # Never silently complete the model's truncated word to manufacture a match.
        truncated = answer.removesuffix('ignancy.')
        self.assertFalse(select_evidence(note, question, truncated)['evidence_matches'])

    def test_procedure_and_exact_highlight(self):
        note = 'DIAGNOSIS:\nBasal cell carcinoma.\nPROCEDURE:\nXylocaine 2% with epinephrine was injected.'
        result = select_evidence(note, 'What was injected?', 'Xylocaine 2% with epinephrine was injected.')
        self.assertEqual(result['evidence_section'], 'PROCEDURE:')
        self.assertEqual(note[result['evidence_start']:result['evidence_end']], result['evidence_text'])
        self.assertEqual(highlighted_context(note, result).count('<mark '), 1)

    def test_repeated_sentence_shows_all_occurrences(self):
        note = 'Aspirin 5 mg was given. Aspirin 5 mg was given.'
        result = select_evidence(note, 'What was given?', 'Aspirin 5 mg was given.')
        self.assertEqual(result['evidence_status'], 'multiple_matches_review_required')
        self.assertEqual(len(result['evidence_matches']), 2)
        self.assertIsNone(result['evidence_text'])
        self.assertEqual(highlighted_context(note, result).count('<mark '), 2)

    def test_dose_and_negation(self):
        for note, answer in [('Aspirin 5 mg was given.', 'Aspirin 10 mg was given.'),
                             ('No aspirin 5 mg was given.', 'Aspirin 5 mg was given.')]:
            self.assertIsNone(select_evidence(note, 'What was given?', answer)['evidence_text'])

    def test_planned_and_incomplete_answers(self):
        for note, answer in [('An ultrasound of the abdomen will be performed tomorrow.', 'An ultrasound of the abdomen was performed.'),
                             ('He should undergo bone marrow aspiration and biopsy.', 'Bone marrow aspiration and biopsy was performed.'),
                             ('Excision (0.8 cm) with reconstruction.', 'Excision (0.8 cm) with reconstruction (')]:
            self.assertIsNone(select_evidence(note, 'What procedure was performed?', answer)['evidence_text'])

    def test_decimal(self):
        result = select_evidence('Dose: 2.5 mg aspirin was given.', 'What was given?', '2.5 mg aspirin.')
        self.assertEqual(result['evidence_section'], 'Dose:')

    def test_html_and_offset_validation(self):
        note = 'PROCEDURE:\nAspirin 5 mg was given.\n<script>alert(1)</script>'
        result = select_evidence(note, 'What was given?', 'Aspirin 5 mg was given.')
        self.assertNotIn('<script>', highlighted_context(note, result))
        with self.assertRaises(ValueError):
            highlighted_context('Different note', result)

    def test_partial_conditions_list(self):
        note = ('Description:\nMesothelioma, pleural effusion, atrial fibrillation, '
                'anemia, ascites, esophageal reflux, and history of deep venous thrombosis.')
        answer = 'The patient has mesothelioma, pleural effusion, atrial fibrillation, anemia, ascites'
        result = select_evidence(note, 'Which conditions are listed in the description?', answer)
        self.assertEqual(result['evidence_status'], 'partial_match_review_required')
        self.assertEqual(result['evidence_text'], note.split('\n')[1])
        self.assertIn('may be incomplete', result['evidence_reason'])
        self.assertEqual(highlighted_context(note, result).count('<mark '), 1)
        self.assertNotIn('esophageal reflux', answer)

    def test_complete_conditions_list(self):
        source = 'Mesothelioma, pleural effusion, and anemia.'
        result = select_evidence('Description:\n' + source,
                                 'Which conditions are listed in the description?', source)
        self.assertEqual(result['evidence_status'], 'lexical_match_review_required')

    def test_specific_question_does_not_require_whole_list(self):
        note = 'Description:\nMesothelioma, pleural effusion, and anemia.'
        result = select_evidence(note, 'What accompanied mesothelioma?', 'Pleural effusion.')
        self.assertEqual(result['evidence_status'], 'lexical_match_review_required')

    def test_three_sections_are_not_capped_at_two(self):
        note = 'Description:\nAspirin 5 mg was given.\nHISTORY:\nAspirin 5 mg was given.\nTREATMENT:\nAspirin 5 mg was given.'
        result = select_evidence(note, 'What was given?', 'Aspirin 5 mg was given.')
        self.assertEqual(len(result['evidence_matches']), 3)
        self.assertEqual(len({r['evidence_start'] for r in result['evidence_matches']}), 3)
        self.assertEqual(highlighted_context(note, result).count('class="evidence-match"'), 3)

    def test_unanswered_list_items_are_not_highlighted(self):
        note = 'Description:\nMesothelioma, pleural effusion, anemia, ascites, esophageal reflux.'
        answer = 'Mesothelioma, pleural effusion, anemia, ascites.'
        result = select_evidence(note, 'Which conditions are listed?', answer)
        from html.parser import HTMLParser
        class Marks(HTMLParser):
            def __init__(self): super().__init__(); self.inside = False; self.text = ''
            def handle_starttag(self, tag, attrs):
                if tag == 'mark': self.inside = True
            def handle_endtag(self, tag):
                if tag == 'mark': self.inside = False
            def handle_data(self, data):
                if self.inside: self.text += data
        parser = Marks(); rendered = highlighted_context(note, result); parser.feed(rendered)
        self.assertIn('esophageal reflux', rendered)
        self.assertNotIn('esophageal reflux', parser.text)
        self.assertIn('ascites', parser.text)

    def test_invalid_highlight_offsets_rejected(self):
        note = 'Aspirin 5 mg was given.'
        result = select_evidence(note, 'What was given?', note)
        result['evidence_matches'][0]['highlight_spans'] = [[0, len(note) + 10]]
        with self.assertRaises(ValueError): highlighted_context(note, result)

    def test_mediport_reason_matches_original_source(self):
        from pathlib import Path
        note = (Path(__file__).resolve().parents[1] / 'mt_onc_50/mt_oncology_27.txt').read_text()
        answer = 'A MediPort was placed because the patient needed chemotherapy.'
        result = select_evidence(note, 'Why was a MediPort placed?', answer)
        matches = [m for m in result['evidence_matches'] if m['evidence_text'] == 'Needs chemotherapy.']
        self.assertTrue(matches)
        for match in matches:
            self.assertEqual([note[a:b] for a, b in match['highlight_spans']], ['Needs chemotherapy'])
        self.assertIn('Needs chemotherapy</mark>', highlighted_context(note, result))
        self.assertEqual(answer, 'A MediPort was placed because the patient needed chemotherapy.')

    def test_simple_inflections_in_both_directions(self):
        for source, answer in [('Requires chemotherapy.', 'Required chemotherapy.'),
                               ('Required chemotherapy.', 'Requires chemotherapy.'),
                               ('Received aspirin 5 mg.', 'Receives aspirin 5 mg.'),
                               ('Multiple tumors were removed.', 'Multiple tumor was removed.')]:
            with self.subTest(source=source):
                result = select_evidence(source, 'What happened?', answer)
                self.assertTrue(result['evidence_matches'])
                self.assertIn('<mark ', highlighted_context(source, result))

    def test_inflections_preserve_negation_and_dose(self):
        for source, answer in [('Does not need chemotherapy.', 'Needed chemotherapy.'),
                               ('Never needed chemotherapy.', 'Needs chemotherapy.'),
                               ('Received aspirin 10 mg.', 'Receives aspirin 5 mg.'),
                               ('Will receive aspirin 5 mg tomorrow.', 'Received aspirin 5 mg.')]:
            with self.subTest(source=source):
                self.assertFalse(select_evidence(source, 'What happened?', answer)['evidence_matches'])

    def test_different_actions_are_not_synonyms(self):
        result = select_evidence('Needs chemotherapy.', 'What happened?', 'Received chemotherapy.')
        self.assertFalse(result['evidence_matches'])

    def test_unlisted_words_and_numbers_stay_exact(self):
        from evidence import terms
        self.assertEqual(terms('mass metastasis insulin 2.5'), ['mass', 'metastasis', 'insulin', '2.5'])

    def test_inflected_repeats_show_every_match(self):
        note = 'Description:\nNeeds chemotherapy.\nHISTORY:\nNeeded chemotherapy.'
        result = select_evidence(note, 'What care is needed?', 'The patient requires chemotherapy.')
        self.assertFalse(result['evidence_matches'])  # No need/require synonym expansion.
        result = select_evidence(note, 'Why was a port placed?', 'The patient needed chemotherapy.')
        self.assertEqual(len(result['evidence_matches']), 2)

    def test_unknown_answer(self):
        self.assertIsNone(select_evidence('', 'What happened?', 'Unknown')['evidence_text'])

    def test_client_empty_input_without_worker(self):
        client = QAClient(python_path='/does/not/exist')
        for question, context in [('', 'note'), ('question', '')]:
            with self.assertRaises(QAError):
                client.ask(question, context)
        self.assertIsNone(client.process)

    def test_missing_environment(self):
        client = QAClient(python_path='/does/not/exist')
        with self.assertRaisesRegex(QAError, 'licensed Python environment is missing'):
            client.ask('What happened?', 'A note.')


if __name__ == '__main__':
    unittest.main()
