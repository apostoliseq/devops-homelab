import sys
import os

# Make app.py importable from this tests/ subdirectory.
# pytest runs from the project root, so without this, `import app` would fail.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
