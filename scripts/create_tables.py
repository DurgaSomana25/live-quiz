#!/usr/bin/env python3
"""Create all database tables using app.database.Base.metadata.create_all

Run with the project's venv active:
    python scripts/create_tables.py
"""
import os
import sys

# Ensure project root is on sys.path so `import app` works when running
# this script from the `scripts/` directory.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.config import settings
from app.database import Base, engine

def main():
    print("Using DATABASE_URL:", settings.DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    print("Tables created (if not already present).")

if __name__ == '__main__':
    main()
