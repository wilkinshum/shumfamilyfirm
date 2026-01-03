import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"
if SRC.exists():
    sys.path.append(str(SRC))
