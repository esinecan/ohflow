The failing test was `test_add` in test_calc.py, because `add()` in calc.py returned `a - b` instead of the sum.
Changed the return statement in `add()` to `a + b`; all 2 tests now pass.
