"""UI validation tests; model answers are verified by smoke_test.py, not mocked."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from streamlit.testing.v1 import AppTest
from qa_client import QAError

APP = Path(__file__).with_name('app.py')


class AppTests(unittest.TestCase):
    def test_notes_and_blank_question(self):
        app = AppTest.from_file(str(APP)).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.selectbox[0].options), 50)
        app.button[0].click().run()
        self.assertEqual(app.warning[0].value, 'Enter an English question before submitting.')

    def test_empty_note(self):
        original = Path.read_text

        def read_text(path, *args, **kwargs):
            if path.name == 'mt_oncology_0.txt':
                return '   '
            return original(path, *args, **kwargs)

        with patch.object(Path, 'read_text', read_text):
            app = AppTest.from_file(str(APP)).run()
            app.text_input[0].set_value('What happened?')
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.warning[0].value, 'The selected note is empty. Select another note.')

    def test_qa_error_is_visible(self):
        # Only simulate a failure; never provide a synthetic model answer.
        with patch('qa_client.QAClient.ask', side_effect=QAError('The local QA model is unavailable.')):
            app = AppTest.from_file(str(APP)).run()
            app.text_input[0].set_value('What happened?')
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.error[0].value, 'The local QA model is unavailable.')


if __name__ == '__main__':
    unittest.main()
