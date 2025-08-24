from studytimer.tracker import StudyTracker
from studytimer.telegram_notifier import TelegramNotifier
from studytimer.gui import StudyGUI
from studytimer.scheduler import StudyScheduler


def main() -> None:
    tracker = StudyTracker()
    notifier = TelegramNotifier()
    scheduler = StudyScheduler(tracker, notifier)
    scheduler.start()
    app = StudyGUI(tracker, notifier)
    app.run()


if __name__ == "__main__":
    main()
