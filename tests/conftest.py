import sys
from pathlib import Path

# pyproject.toml의 packages=["common", "vendors"]로 `pip install -e .`하면 필요 없지만,
# 설치 없이 바로 `pytest`를 돌릴 수 있도록 run.py와 동일한 방식으로 repo root를 sys.path에 넣는다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
