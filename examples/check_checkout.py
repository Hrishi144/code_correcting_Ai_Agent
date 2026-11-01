"""Run checkout checks explicitly on a reviewed Python file."""

from pathlib import Path
import sys

# Allow direct execution from an unpacked source checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_agent.checkout_checks import main, run_checks


if __name__ == "__main__":
    raise SystemExit(main())
