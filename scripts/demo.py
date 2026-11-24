# -*- coding: utf-8 -*-
"""Development wrapper for `fin-evidence demo`."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from fin_evidence.demo import main  # noqa: E402

if __name__ == '__main__':
    raise SystemExit(main())
