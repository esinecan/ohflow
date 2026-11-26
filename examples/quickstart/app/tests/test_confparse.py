import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from confparse import ConfigError, parse


class ParseTest(unittest.TestCase):
    def test_typed_values(self):
        config = parse("name = api\nport = 8080\ndebug = yes\n")
        self.assertEqual(config, {"name": "api", "port": 8080, "debug": True})

    def test_comments_and_blank_lines(self):
        self.assertEqual(parse("# a comment\n\nworkers = 4  # four\n"), {"workers": 4})

    def test_unknown_key_is_kept_as_text(self):
        self.assertEqual(parse("colour = blue\n"), {"colour": "blue"})

    def test_bad_number_names_its_line(self):
        with self.assertRaises(ConfigError) as caught:
            parse("name = api\nport = eighty\n")
        self.assertEqual(caught.exception.line, 2)
        self.assertIn("line 2", str(caught.exception))

    def test_line_without_equals(self):
        with self.assertRaises(ConfigError):
            parse("debug\n")


if __name__ == "__main__":
    unittest.main()
