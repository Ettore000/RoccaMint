from __future__ import annotations
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict

class StudyTracker:
    """Track study sessions and compute time summaries."""

    def __init__(self, log_file: str | Path = "study_log.json") -> None:
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            self.log_file.write_text("[]")
        self.current_start: datetime | None = None

    # session management -------------------------------------------------
    def start(self) -> None:
        """Mark the beginning of a study session."""
        self.current_start = datetime.now()

    def stop(self) -> float:
        """End current session and return duration in minutes."""
        if not self.current_start:
            return 0.0
        end = datetime.now()
        minutes = (end - self.current_start).total_seconds() / 60
        self._append_session(self.current_start, end, minutes)
        self.current_start = None
        return minutes

    # log handling -------------------------------------------------------
    def _append_session(self, start: datetime, end: datetime, minutes: float) -> None:
        data: List[Dict[str, str]] = json.loads(self.log_file.read_text())
        data.append({
            "start": start.isoformat(),
            "end": end.isoformat(),
            "minutes": minutes,
        })
        self.log_file.write_text(json.dumps(data))

    def _sessions(self) -> List[Dict[str, datetime]]:
        raw = json.loads(self.log_file.read_text())
        sessions = []
        for item in raw:
            sessions.append({
                "start": datetime.fromisoformat(item["start"]),
                "end": datetime.fromisoformat(item["end"]),
                "minutes": float(item["minutes"]),
            })
        return sessions

    # summaries ----------------------------------------------------------
    def _total_in_range(self, start: date, end: date) -> float:
        total = 0.0
        for s in self._sessions():
            day = s["start"].date()
            if start <= day < end:
                total += s["minutes"]
        return total

    def daily_total(self, day: date | None = None) -> float:
        day = day or date.today()
        return self._total_in_range(day, day + timedelta(days=1))

    def weekly_total(self, day: date | None = None) -> float:
        day = day or date.today()
        start = day - timedelta(days=day.weekday())
        end = start + timedelta(days=7)
        return self._total_in_range(start, end)

    def monthly_total(self, day: date | None = None) -> float:
        day = day or date.today()
        start = day.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return self._total_in_range(start, end)

    def yearly_total(self, day: date | None = None) -> float:
        day = day or date.today()
        start = date(day.year, 1, 1)
        end = date(day.year + 1, 1, 1)
        return self._total_in_range(start, end)
