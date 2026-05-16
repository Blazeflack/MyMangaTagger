# gui/augment_metadata_dialog.py

"""Dialogs for volume metadata augmentation.

This module contains a small URL prompt and a preview dialog used by the
publisher-specific volume augmentation workflow.
"""

import tkinter as tk
import ttkbootstrap as tb
from typing import Any

import services.constants as constants
from augmenters.base import VolumeAugmentationPreviewRow
from gui.utils import center_window_on_parent


class AugmentMetadataUrlDialog(tk.Toplevel):
    """Modal dialog for entering a publisher series URL.

    Args:
        parent: Parent Tkinter window.
        selected_count: Number of selected files that may be augmented.

    Attributes:
        result: Entered URL, or None when cancelled.
    """

    def __init__(self, parent: tk.Tk | tk.Toplevel, selected_count: int) -> None:
        """Initialize the URL dialog.

        Args:
            parent: Parent Tkinter window.
            selected_count: Number of selected files that may be augmented.
        """
        super().__init__(parent)
        self.style = getattr(parent, "style", tb.Style.get_instance())
        self.result: str | None = None
        self.url_var = tk.StringVar()

        self.title("Augment Metadata")
        self.resizable(False, False)
        self.geometry("1x1+10000+10000")
        self.withdraw()

        center_window_on_parent(
            parent,
            self,
            constants.AUGMENT_URL_DIALOG_WIDTH,
            constants.AUGMENT_URL_DIALOG_HEIGHT,
        )

        self.transient(parent)
        self.grab_set()

        outer = tb.Frame(self, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        tb.Label(
            outer,
            text="Augment selected files with publisher volume metadata",
            font=constants.DEFAULT_FONT_BOLD,
        ).pack(anchor=tk.W, pady=(0, 10))

        tb.Label(
            outer,
            text=(
                f"{selected_count} selected file(s). Enter a publisher series URL "
                "from J-Novel Club, Yen Press, Seven Seas, or Kodansha USA."
            ),
            wraplength=620,
        ).pack(anchor=tk.W, pady=(0, 10))

        tb.Label(outer, text="Publisher series URL:").pack(anchor=tk.W)
        self.url_entry = tb.Entry(outer, textvariable=self.url_var, width=80)
        self.url_entry.pack(fill=tk.X, pady=(4, 14))
        self.url_entry.bind("<Return>", lambda _event: self._on_ok())

        button_row = tb.Frame(outer)
        button_row.pack(anchor=tk.E)

        tb.Button(button_row, text="Fetch Preview", command=self._on_ok).pack(side=tk.LEFT, padx=(0, 8))
        tb.Button(button_row, text="Cancel", command=self._on_cancel).pack(side=tk.LEFT)

        self.bind("<Escape>", lambda _event: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.update_idletasks()
        self.deiconify()
        self.url_entry.focus_set()
        self.wait_window()

    def _on_ok(self) -> None:
        """Store the entered URL and close the dialog."""
        url = self.url_var.get().strip()
        if not url:
            return
        self.result = url
        self.destroy()

    def _on_cancel(self) -> None:
        """Cancel the dialog without returning a URL."""
        self.result = None
        self.destroy()


class AugmentMetadataPreviewDialog(tk.Toplevel):
    """Modal preview dialog for volume metadata augmentation.

    Args:
        parent: Parent Tkinter window.
        rows: Preview rows to display.
        augmenter_name: Human-friendly publisher augmenter name.

    Attributes:
        result: True when the user clicks Apply, otherwise False.
    """

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        rows: list[VolumeAugmentationPreviewRow],
        augmenter_name: str,
    ) -> None:
        """Initialize the preview dialog.

        Args:
            parent: Parent Tkinter window.
            rows: Preview rows to display.
            augmenter_name: Human-friendly publisher augmenter name.
        """
        super().__init__(parent)
        self.style = getattr(parent, "style", tb.Style.get_instance())
        self.result = False
        self.rows = rows
        self.augmenter_name = augmenter_name

        self.title("Augment Metadata Preview")
        self.resizable(True, True)
        self.geometry("1x1+10000+10000")
        self.withdraw()

        center_window_on_parent(
            parent,
            self,
            constants.AUGMENT_PREVIEW_DIALOG_WIDTH,
            constants.AUGMENT_PREVIEW_DIALOG_HEIGHT,
        )

        self.transient(parent)
        self.grab_set()

        self._build_ui()

        self.bind("<Escape>", lambda _event: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.update_idletasks()
        self.deiconify()
        self.wait_window()

    def _build_ui(self) -> None:
        """Build the preview dialog widgets."""
        outer = tb.Frame(self, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        tb.Label(
            outer,
            text=f"Preview volume metadata patches from {self.augmenter_name}",
            font=constants.DEFAULT_FONT_BOLD,
        ).pack(anchor=tk.W, pady=(0, 8))

        tb.Label(
            outer,
            text="Only title, summary, year, month, and day can be changed.",
            font=constants.DEFAULT_FONT_ITALIC,
        ).pack(anchor=tk.W, pady=(0, 10))

        table_frame = tb.Frame(outer)
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = (
            "file",
            "number",
            "title_before",
            "title_after",
            "summary",
            "date_before",
            "date_after",
            "status",
        )
        self.tree = tb.Treeview(table_frame, columns=columns, show="headings", height=14)
        headings = {
            "file": "File",
            "number": "Number",
            "title_before": "Title before",
            "title_after": "Title after",
            "summary": "Summary",
            "date_before": "Date before",
            "date_after": "Date after",
            "status": "Status",
        }
        widths = {
            "file": 220,
            "number": 70,
            "title_before": 240,
            "title_after": 260,
            "summary": 90,
            "date_before": 100,
            "date_after": 100,
            "status": 170,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], minwidth=50, stretch=True)

        y_scroll = tb.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = tb.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        for row in self.rows:
            self.tree.insert(
                "",
                tk.END,
                values=(
                    row.path.name,
                    row.number,
                    row.title_before,
                    row.title_after,
                    row.summary_status,
                    row.date_before,
                    row.date_after,
                    row.status,
                ),
            )

        button_row = tb.Frame(outer)
        button_row.pack(fill=tk.X, pady=(12, 0))

        apply_enabled = any(row.status.startswith("Changed") or row.status == "Matched" for row in self.rows)
        tb.Button(
            button_row,
            text="Apply",
            command=self._on_apply,
            state=tk.NORMAL if apply_enabled else tk.DISABLED,
        ).pack(side=tk.RIGHT, padx=(8, 0))
        tb.Button(button_row, text="Cancel", command=self._on_cancel).pack(side=tk.RIGHT)

    def _on_apply(self) -> None:
        """Confirm that the displayed patches should be applied."""
        self.result = True
        self.destroy()

    def _on_cancel(self) -> None:
        """Close the dialog without applying patches."""
        self.result = False
        self.destroy()