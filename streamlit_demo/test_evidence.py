"""Regression tests for provenance, ambiguity, and safe HTML rendering."""
import unittest
from evidence import select_evidence, highlighted_context
from qa_client import QAClient, QAError


class EvidenceTests(unittest.TestCase):
    def test_procedure_and_exact_highlight(self):
        note = 'DIAGNOSIS:\nBasal cell carcinoma.\nPROCEDURE:\nXylocaine 2% with epinephrine was injected.'
        result = select_evidence(note, 'What was injected?', 'Xylocaine 2% with epinephrine was injected.')
        self.assertEqual(result['evidence_section'], 'PROCEDURE:')
        self.assertEqual(note[result['evidence_start']:result['evidence_end']], result['evidence_text'])
        self.assertEqual(highlighted_context(note, result).count('<mark '), 1)

    def test_repeated_sentence_abstains(self):
        note = 'Aspirin 5 mg was given. Aspirin 5 mg was given.'
        result = select_evidence(note, 'What was given?', 'Aspirin 5 mg was given.')
        self.assertEqual(result['evidence_status'], 'ambiguous')
        self.assertNotIn('<mark', highlighted_context(note, result))

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
