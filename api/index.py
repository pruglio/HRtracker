import sys
import os

# Add project root to path so `import app` finds app.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

handler = app
