# gui/log_viewer.py

"""Log viewer window implementation for the MyMangaTagger application.

This module defines a LogViewer class that provides a pop-up window
to display application logs with filtering by level, search,
auto-refresh, and clearing capabilities.
"""

import tkinter as tk
import ttkbootstrap as tb
from typing import Any

import services.constants as constants
from gui.utils import center_window_on_parent
from services.logger import get_logs, clear_logs


class LogViewer(tk.Toplevel):
    """A window to display and interact with application logs.

    Provides controls to filter by log level, search within log messages,
    auto-refresh the view when new entries appear, and clear the logs.

    Attributes:
        level_var: Tkinter variable storing the selected log level filter.
        search_var: Tkinter variable storing the search term.
        auto_refresh_var: Tkinter variable indicating auto-refresh toggle state.
        text: Text widget used to display formatted log entries.
        _last_count: Number of log entries last displayed, for change detection.
    """

    def __init__(self, parent: tk.Tk | tk.Toplevel, style: tb.Style) -> None:
        """Initialize the LogViewer window.

        Args:
            parent: The parent widget for this toplevel window.
            style (tb.Style): The style object for widget theming and styling.
        """
        super().__init__(parent)
        self.style = style
        self.title(constants.LOG_VIEWER_TITLE)
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.configure(padx=10, pady=10)

        # Center the log viewer window on its parent.
        center_window_on_parent(
            parent,
            self,
            constants.LOG_VIEWER_WIDTH,
            constants.LOG_VIEWER_HEIGHT
        )

        # Variables for filter controls.
        self.level_var = tk.StringVar(value="DEBUG")
        self.search_var = tk.StringVar()
        self.auto_refresh_var = tk.BooleanVar(value=True)

        # Build the filter controls row.
        controls_frame = tb.Frame(self)
        controls_frame.pack(fill=tk.X, pady=(0, 6))

        # Label for OptionMenu
        tb.Label(controls_frame, text="Level:").pack(side=tk.LEFT)
        # Choices for the OptionMenu
        levels = ["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"]

        # Create the OptionMenu
        om = tb.OptionMenu(
            controls_frame,
            self.level_var,
            self.level_var.get() or levels[0],  # Set initial value, fallback to first if empty
            *levels,
        )
        om.configure(width=12, bootstyle="info-outline")
        om.pack(side=tk.LEFT, padx=5)

        # Bind selection change (OptionMenu uses variable trace)
        self.level_var.trace_add("write", lambda *a: self._refresh())

        tb.Checkbutton(
            controls_frame,
            text="Auto-Refresh",
            variable=self.auto_refresh_var
        ).pack(side=tk.LEFT, padx=20)

        tb.Label(controls_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))
        search_entry = tb.Entry(
            controls_frame,
            textvariable=self.search_var,
            width=30
        )
        search_entry.pack(side=tk.LEFT)
        search_entry.bind("<Return>", lambda e: self._refresh())

        tb.Button(
            controls_frame,
            text="Clear Log",
            command=self._clear_log
        ).pack(side=tk.RIGHT)

        # Prepare the text widget to display log entries.
        self.text = tk.Text(
            self,
            state="disabled",
            wrap="none",
            font=constants.CONSOLE_FONT
        )
        self.text.pack(fill=tk.BOTH, expand=True)

        # Configure text tags for different log levels with colors.
        level_colors = [
            ("DEBUG", self.style.colors.light),
            ("INFO", self.style.colors.info),
            ("WARN", self.style.colors.warning),
            ("ERROR", self.style.colors.danger),
            ("CRITICAL", self.style.colors.danger),
        ]
        for level, color in level_colors:
            self.text.tag_configure(level, foreground=color)

        # Track last number of log entries to detect updates.
        self._last_count = 0

        # Initial population of log entries.
        self._refresh()
        # Start the auto-refresh loop.
        self._auto_refresh()

    def _refresh(self, *args: Any) -> None:
        """Reload and display log entries based on current filters.

        Args:
            *args: Unused positional arguments for compatibility with callbacks.
        """
        # Retrieve logs filtered by level.
        logs = get_logs(self.level_var.get())
        search_term = self.search_var.get().lower()

        # Enable text widget for editing.
        self.text.config(state="normal")
        # Clear existing content.
        self.text.delete("1.0", tk.END)

        # Insert filtered log entries.
        for timestamp, level, message in logs:
            if search_term and search_term not in message.lower():
                continue
            tag = level if level in self.text.tag_names() else "INFO"
            self.text.insert(
                tk.END,
                f"[{timestamp}] [{level}] {message}\n",
                tag
            )

        # Disable editing and scroll to the end.
        self.text.config(state="disabled")
        self.text.yview(tk.END)
        # Update last count for change detection.
        self._last_count = len(logs)

    def _auto_refresh(self) -> None:
        """Periodically check for new log entries and refresh if needed."""
        # If auto-refresh is enabled and new logs exist, refresh.
        if self.auto_refresh_var.get() and len(get_logs("DEBUG")) != self._last_count:
            self._refresh()
        # Schedule next check in 1 second.
        self.after(1000, self._auto_refresh)

    def _clear_log(self) -> None:
        """Clear all log entries and refresh the display."""
        clear_logs()
        self._refresh()

    def _on_close(self) -> None:
        """Handle window close event by destroying and clearing reference."""
        self.destroy()
        # Remove reference from parent if present to allow reopening.
        if hasattr(self.master, "log_viewer"):
            self.master.log_viewer = None
