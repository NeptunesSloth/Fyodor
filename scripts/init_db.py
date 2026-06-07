#!/usr/bin/env python
"""Create the database tables. Idempotent; safe to re-run."""

from fyodor.db import init_db

if __name__ == "__main__":
    init_db()
    print("Fyodor database initialised.")
