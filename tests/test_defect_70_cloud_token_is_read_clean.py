"""Defect 70: a `PI_CLOUD_TOKEN` with a byte order mark broke every request.

A token copied from a file a Windows editor wrote starts with U+FEFF, and a
token read with `$(cat file)` in some shells ends with a line break. The
`Authorization` header then failed to encode, and preflight said
`UnicodeEncodeError: 'latin-1' codec can't encode character '\\ufeff'`.

Both readers of the variable now drop a leading byte order mark and the
whitespace around the token.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from unittest import mock

from ohflow import pi_cloud_runner
from support import TempCase

CLIENT_PATH = Path(pi_cloud_runner.__file__).with_name("pi_cloud_client.py")


def _client():
    spec = importlib.util.spec_from_file_location("pi_cloud_client_d70", CLIENT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TheCloudTokenIsReadClean(TempCase):

    def _both(self):
        return (pi_cloud_runner.read_token, _client().read_token)

    def test_a_byte_order_mark_and_a_line_break_are_dropped(self):
        for read in self._both():
            with mock.patch.dict(os.environ, {"PI_CLOUD_TOKEN": "﻿abc-123\r\n"}):
                self.assertEqual(read(), "abc-123")
            with mock.patch.dict(os.environ, {"PI_CLOUD_TOKEN": "  abc-123 "}):
                self.assertEqual(read(), "abc-123")

    def test_a_clean_token_is_unchanged_and_an_empty_one_is_empty(self):
        for read in self._both():
            with mock.patch.dict(os.environ, {"PI_CLOUD_TOKEN": "abc-123"}):
                self.assertEqual(read(), "abc-123")
            with mock.patch.dict(os.environ, {"PI_CLOUD_TOKEN": "﻿ \n"}):
                self.assertEqual(read(), "")
            with mock.patch.dict(os.environ):
                os.environ.pop("PI_CLOUD_TOKEN", None)
                self.assertEqual(read(), "")


if __name__ == "__main__":
    import unittest
    unittest.main()
