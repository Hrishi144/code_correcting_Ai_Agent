"""Fixed checkout checks. Executing a file uses normal permissions, not a sandbox."""

import argparse
import io
import json
from pathlib import Path
import runpy
import sys
import unittest

CHECKOUT_CONTRACT = (
    "checkout(items,discount_percent=0,tax_percent=0) returns subtotal,discount,tax,total. "
    "Price>=0, quantity>0, discount 0..100%, tax>=0%. Sum price*quantity; tax after discount. "
    "Cart 200*2+100*1 at 10% discount/tax: 500,50,45,495. Empty cart: zeros."
)


class CheckoutChecks(unittest.TestCase):
    def __init__(self, method_name, checkout):
        super().__init__(method_name)
        self.checkout = checkout

    @staticmethod
    def cart():
        return [
            {"name": "Keyboard", "price": 200, "quantity": 2},
            {"name": "Mouse", "price": 100, "quantity": 1},
        ]

    def test_discount_and_tax(self):
        self.assertEqual(
            self.checkout(self.cart(), discount_percent=10, tax_percent=10),
            {"subtotal": 500, "discount": 50, "tax": 45, "total": 495},
        )

    def test_no_discount_or_tax(self):
        self.assertEqual(
            self.checkout(self.cart()),
            {"subtotal": 500, "discount": 0, "tax": 0, "total": 500},
        )

    def test_empty_cart(self):
        self.assertEqual(
            self.checkout([], discount_percent=10, tax_percent=10),
            {"subtotal": 0, "discount": 0, "tax": 0, "total": 0},
        )

    def test_full_discount(self):
        self.assertEqual(
            self.checkout(self.cart(), discount_percent=100, tax_percent=10),
            {"subtotal": 500, "discount": 500, "tax": 0, "total": 0},
        )

    def test_nonpositive_quantity(self):
        for quantity in (0, -1):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.checkout([{"price": 100, "quantity": quantity}])

    def test_negative_price(self):
        with self.assertRaises(ValueError):
            self.checkout([{"price": -1, "quantity": 1}])

    def test_invalid_discount(self):
        for discount in (-1, 101):
            with self.subTest(discount=discount), self.assertRaises(ValueError):
                self.checkout(self.cart(), discount_percent=discount)

    def test_negative_tax(self):
        with self.assertRaises(ValueError):
            self.checkout(self.cart(), tax_percent=-1)


def run_checks(checkout, *, stream=None):
    names = unittest.defaultTestLoader.getTestCaseNames(CheckoutChecks)
    suite = unittest.TestSuite(CheckoutChecks(name, checkout) for name in names)
    return unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="Reviewed Python file defining checkout(items, discount_percent=0, tax_percent=0)")
    args = parser.parse_args(argv)
    if args.file.suffix.lower() != ".py" or not args.file.is_file():
        parser.error("Select an existing .py file.")
    print(f"Executing reviewed file for checkout tests: {args.file.resolve()}", flush=True)
    try:
        namespace = runpy.run_path(str(args.file.resolve()))
        checkout = namespace.get("checkout")
        if not callable(checkout):
            raise ValueError("Selected file must define a callable checkout function.")
    except Exception as exc:
        print(f"Could not load checkout: {exc}", file=sys.stderr)
        return 1
    return 0 if run_checks(checkout).wasSuccessful() else 1


def worker_main():
    """Write a compact report; program stdout/stderr is discarded by the parent."""
    source, report_path = map(Path, sys.argv[1:])
    try:
        namespace = runpy.run_path(str(source))
        checkout = namespace.get("checkout")
        if not callable(checkout):
            raise ValueError("Missing callable checkout function")
        result = run_checks(checkout, stream=io.StringIO())
        failed_names = sorted({
            getattr(case, "test_case", case)._testMethodName
            for case, _ in result.failures + result.errors
        })
        complete = result.testsRun == 8 and not result.skipped and not result.expectedFailures
        passed = complete and result.wasSuccessful()
        detail = "8 checkout checks passed; other behavior and instruction compliance were not checked."
        if not passed:
            detail = "Checkout failed: " + ", ".join(failed_names)
            if result.errors:
                detail += ". " + result.errors[0][1].strip().splitlines()[-1][:120]
            if not complete:
                detail += ". Not all 8 checks completed."
        report = {"status": "passed" if passed else "failed", "detail": detail,
                  "tests_run": result.testsRun}
    except (Exception, SystemExit) as exc:
        report = {"status": "failed", "detail": f"Checkout could not load: {type(exc).__name__}: {str(exc)[:160]}",
                  "tests_run": 0}
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(worker_main())
