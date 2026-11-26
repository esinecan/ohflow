"""Defect 52: `workflow.py` exported a name it never defined.

What went wrong. `ohflow/workflow.py` listed `dumps` in `__all__`, and the module
has no `dumps`. Python resolves every name in `__all__` on a star import, so
`from ohflow.workflow import *` raised AttributeError. No caller used `dumps`;
`to_jsonable` is the serialiser the engine calls.

What is asserted here. Every name that any `ohflow` module lists in `__all__`
exists in that module, which is what a star import needs, so the fault cannot
come back in `workflow.py` or in another module.
"""

from __future__ import annotations

import importlib
import pkgutil
import unittest

import ohflow


class EveryExportedNameExists(unittest.TestCase):

    def test_every_name_in_every_all_is_defined(self):
        missing = []
        for info in pkgutil.iter_modules(ohflow.__path__):
            module = importlib.import_module(f"ohflow.{info.name}")
            for name in getattr(module, "__all__", ()):
                if not hasattr(module, name):
                    missing.append(f"ohflow.{info.name}.{name}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
