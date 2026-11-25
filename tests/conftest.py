import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("tools/mohs2", "tools/clip"):
    sys.path.insert(0, os.path.join(ROOT, sub))
