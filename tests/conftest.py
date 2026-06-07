import os
import tempfile

# Point the database at a throwaway SQLite file BEFORE fyodor.db is imported,
# so tests never touch a real database.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["FYODOR_DATABASE_URL"] = f"sqlite:///{_tmp.name}"
