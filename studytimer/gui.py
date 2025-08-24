from __future__ import annotations
import tkinter as tk
from datetime import datetime
from tracker import StudyTracker
from telegram_notifier import TelegramNotifier

class StudyGUI:
    """Tkinter interface with ON/OFF button and timer."""

    def __init__(self, tracker: StudyTracker, notifier: TelegramNotifier) -> None:
        self.tracker = tracker
        self.notifier = notifier
        self.root = tk.Tk()
        self.root.title("Study Tracker")
        self.is_studying = False

        self.minutes_var = tk.StringVar(value="0")
        self.button = tk.Button(self.root, text="ON", width=20, command=self.toggle)
        self.button.pack(pady=10)
        self.label = tk.Label(self.root, textvariable=self.minutes_var, font=("Arial", 24))
        self.label.pack()
        self._update_clock()

    def toggle(self) -> None:
        if not self.is_studying:
            self.is_studying = True
            self.tracker.start()
            self.notifier.send_message("Sto studiando")
            self.button.config(text="OFF")
        else:
            self.is_studying = False
            minutes = self.tracker.stop()
            self.notifier.send_message(f"Ho studiato {int(minutes)} minuti")
            self.minutes_var.set("0")
            self.button.config(text="ON")

    def _update_clock(self) -> None:
        if self.is_studying and self.tracker.current_start:
            elapsed = (datetime.now() - self.tracker.current_start).total_seconds() // 60
            self.minutes_var.set(str(int(elapsed)))
        self.root.after(1000, self._update_clock)

    def run(self) -> None:
        self.root.mainloop()
