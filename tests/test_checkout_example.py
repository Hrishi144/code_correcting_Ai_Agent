"""Check the example verifier against known fixtures, without calling a model."""

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from examples import check_checkout


CORRECT_SOURCE = '''
def checkout(items, discount_percent=0, tax_percent=0):
    if not 0 <= discount_percent <= 100 or tax_percent < 0:
        raise ValueError("Invalid rate")
    for item in items:
        if item["price"] < 0 or item["quantity"] <= 0:
            raise ValueError("Invalid item")
    subtotal = sum(item["price"] * item["quantity"] for item in items)
    discount = subtotal * discount_percent / 100
    discounted_subtotal = subtotal - discount
    tax = discounted_subtotal * tax_percent / 100
    total = discounted_subtotal + tax
    return dict(subtotal=round(subtotal, 2), discount=round(discount, 2),
                tax=round(tax, 2), total=round(total, 2))
'''


class CheckoutExampleTests(unittest.TestCase):
    def test_correct_checkout_passes_and_source_is_not_rewritten(self):
        with tempfile.TemporaryDirectory(prefix="checkout-test-") as folder:
            path = Path(folder) / "checkout.py"
            path.write_text(CORRECT_SOURCE, encoding="utf-8")
            original = path.read_bytes()
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(check_checkout.main([str(path)]), 0)
            self.assertEqual(path.read_bytes(), original)

    def test_each_reported_logic_bug_fails_despite_valid_syntax(self):
        mutations = (
            ('item["quantity"] <= 0', 'item["quantity"] < 0'),
            ('item["price"] * item["quantity"]', 'item["price"] + item["quantity"]'),
            ('subtotal * discount_percent / 100', 'subtotal * discount_percent'),
            ('tax = discounted_subtotal * tax_percent / 100', 'tax = subtotal * tax_percent / 100'),
            ('total = discounted_subtotal + tax', 'total = subtotal + tax'),
        )
        for before, after in mutations:
            with self.subTest(bug=after):
                source = CORRECT_SOURCE.replace(before, after)
                namespace = {}
                # These are fixed, developer-owned test fixtures, not model output.
                exec(compile(source, "fixture.py", "exec"), namespace)
                result = check_checkout.run_checks(namespace["checkout"], stream=io.StringIO())
                self.assertEqual(result.testsRun, 8)
                self.assertFalse(result.wasSuccessful())

    def test_load_errors_return_failure(self):
        with tempfile.TemporaryDirectory(prefix="checkout-test-") as folder:
            path = Path(folder) / "checkout.py"
            for source in ("def broken(", "x = 1", 'raise RuntimeError("broken import")'):
                with self.subTest(source=source):
                    path.write_text(source, encoding="utf-8")
                    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                        self.assertEqual(check_checkout.main([str(path)]), 1)
                    self.assertIn("Could not load checkout", errors.getvalue())
