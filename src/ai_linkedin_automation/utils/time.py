from datetime import datetime
from typing import Optional


def current_week_id(now: Optional[datetime] = None) -> str:
    current = now or datetime.now()
    year, week, _ = current.isocalendar()
    return f"{year}-W{week:02d}"
