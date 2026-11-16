import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decision_trace.utils.db import get_session
from sqlalchemy import text

with get_session() as s:
    rows = s.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    ).fetchall()
    print(f"Tables created ({len(rows)}):")
    for r in rows:
        print(f"  {r[0]}")
