"""Clear ALL test cases so the SEC dashboard starts empty. Run once before the real demo:  python tools/reset_db.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import db
c = db.conn(); n = c.execute("DELETE FROM cases").rowcount; c.execute("DELETE FROM sqlite_sequence WHERE name='cases'"); c.commit()
print(f"Cleared {n} test cases. Dashboard is now empty.")
