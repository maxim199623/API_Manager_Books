import sys
from pathlib import Path

# Корень проекта: .../
ROOT_DIR = Path(__file__).resolve().parents[1]

# Добавляем корень проекта в sys.path, если его там ещё нет
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))