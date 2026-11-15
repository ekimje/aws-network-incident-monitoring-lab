import sys
from pathlib import Path

# app/ 폴더의 모듈(main, db, collector ...)을 import할 수 있게 한다
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
