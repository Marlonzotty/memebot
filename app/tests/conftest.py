# app/tests/conftest.py
import sys
from pathlib import Path

# /.../memebot-backend - cópia/app/tests/conftest.py -> root = /.../memebot-backend - cópia
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
