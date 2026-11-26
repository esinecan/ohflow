"""The routed documents resolve and every lesson has defined terms and examples."""
import unittest
from check_docs import check


class DocsOnboarding(unittest.TestCase):
    def test_links_word_limit_and_five_glossary_lessons(self):
        errors, _, _, lessons = check()
        self.assertEqual(lessons, 5)
        self.assertEqual(errors, [])
