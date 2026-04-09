import sys
import os
from pathlib import Path

# Add 'src' to the path so the package 'shift_manager' can be imported correctly
src_path = str(Path(__file__).parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from shift_manager.app import main

if __name__ == "__main__":
    main()
