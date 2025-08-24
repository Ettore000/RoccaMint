from __future__ import annotations
from apscheduler.schedulers.background import BackgroundScheduler
from telegram_notifier import TelegramNotifier
from tracker import StudyTracker

class StudyScheduler:
    """Schedule periodic study summaries."""

    def __init__(self, tracker: StudyTracker, notifier: TelegramNotifier) -> None:
        self.tracker = tracker
        self.notifier = notifier
        self.scheduler = BackgroundScheduler()
        self._schedule_jobs()

    def _schedule_jobs(self) -> None:
        self.scheduler.add_job(self.daily_report, "cron", hour=23, minute=59)
        self.scheduler.add_job(self.weekly_report, "cron", day_of_week="sun", hour=23, minute=59)
        self.scheduler.add_job(self.monthly_report, "cron", day="last", hour=23, minute=59)
        self.scheduler.add_job(self.yearly_report, "cron", month="dec", day=31, hour=23, minute=59)

    def start(self) -> None:
        self.scheduler.start()

    def daily_report(self) -> None:
        minutes = self.tracker.daily_total()
        self.notifier.send_message(_format_minutes("Oggi hai studiato", minutes))

    def weekly_report(self) -> None:
        minutes = self.tracker.weekly_total()
        self.notifier.send_message(_format_minutes("Questa settimana hai studiato", minutes))

    def monthly_report(self) -> None:
        minutes = self.tracker.monthly_total()
        self.notifier.send_message(_format_minutes("Questo mese hai studiato", minutes))

    def yearly_report(self) -> None:
        minutes = self.tracker.yearly_total()
        self.notifier.send_message(_format_minutes("Quest'anno hai studiato", minutes))


def _format_minutes(prefix: str, minutes: float) -> str:
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{prefix} {hours} ore e {mins} minuti"
