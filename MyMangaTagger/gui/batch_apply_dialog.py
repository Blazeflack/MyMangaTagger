# gui/batch_apply_dialog.py

"""Batch apply dialog for shared metadata fetch in MyMangaTagger.

This dialog is shown after metadata has been fetched once for multiple selected
files using the "Single URL -> Apply to all" flow. It allows the user to review
or override the fetched base title, choose the starting volume number, and see a
live preview of the generated title format before applying the metadata.
"""

import tkinter as tk
import ttkbootstrap as tb

import services.constants as constants
from gui.utils import center_window_on_parent


class BatchApplyDialog(tk.Toplevel):
    """Modal dialog for configuring batch title numbering.

    Args:
        parent: Parent Tkinter window.
        fetched_title: The title fetched from the metadata source.
        start_number: Initial start number to prefill in the dialog.

    Attributes:
        result: None if cancelled, otherwise a dict with:
            - "base_title": str
            - "start_number": int
    """

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        fetched_title: str,
        start_number: int = 1,
    ) -> None:
        """Initialize the batch apply dialog.

        Args:
            parent: Parent Tkinter window.
            fetched_title: The fetched title to prefill as the base title.
            start_number: Default starting number for auto-numbering.
        """
        super().__init__(parent)

        self.style = getattr(parent, "style", tb.Style.get_instance())
        self.result: dict[str, str | int] | None = None
        self.fetched_title = fetched_title.strip()
        self.title("Batch Apply Options")
        self.resizable(False, False)

        # Hide during setup to avoid visible repositioning.
        self.geometry("1x1+10000+10000")
        self.withdraw()

        center_window_on_parent(
            parent,
            self,
            constants.BATCH_APPLY_DIALOG_WIDTH,
            constants.BATCH_APPLY_DIALOG_HEIGHT,
        )

        self.transient(parent)
        self.grab_set()

        self.base_title_var = tk.StringVar(value=self.fetched_title)
        self.start_number_var = tk.StringVar(value=str(max(1, start_number)))
        # Validation: only allow digits
        vcmd = (self.register(self._validate_number), "%P")
        self.preview_var = tk.StringVar()

        outer = tb.Frame(self, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        tb.Label(
            outer,
            text="Apply shared metadata to selected files",
            font=constants.DEFAULT_FONT_BOLD,
        ).pack(anchor=tk.W, pady=(0, 10))

        tb.Label(
            outer,
            text="Base Title",
            font=constants.FONT_LABEL_BOLD,
        ).pack(anchor=tk.W)
        self.base_title_entry = tb.Entry(
            outer,
            textvariable=self.base_title_var,
            width=50,
        )
        self.base_title_entry.pack(fill=tk.X, pady=(0, 10))
        self.base_title_entry.bind("<KeyRelease>", self._on_value_changed)

        tb.Label(
            outer,
            text="Start Number",
            font=constants.FONT_LABEL_BOLD,
        ).pack(anchor=tk.W)
        self.start_number_entry = tb.Entry(
            outer,
            textvariable=self.start_number_var,
            width=10,
            validate="key",
            validatecommand=vcmd,
        )
        self.start_number_entry.pack(anchor=tk.W, pady=(0, 10))
        self.start_number_entry.bind("<KeyRelease>", self._on_value_changed)

        tb.Label(
            outer,
            text="Preview",
            font=constants.FONT_LABEL_BOLD,
        ).pack(anchor=tk.W)
        tb.Label(
            outer,
            textvariable=self.preview_var,
            foreground=self.style.colors.info if self.style else None,
            wraplength=600,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 14))

        button_row = tb.Frame(outer)
        button_row.pack(anchor="center")

        tb.Button(button_row, text="OK", command=self._on_ok).pack(side=tk.LEFT, padx=(0, 8))
        tb.Button(button_row, text="Cancel", command=self._on_cancel).pack(side=tk.LEFT)


        self._update_preview()

        self.update_idletasks()
        self.deiconify()
        self.base_title_entry.focus_set()
        # Keyboard shortcuts
        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.wait_window()

    def _on_value_changed(self, _event: tk.Event | None = None) -> None:
        """Handle entry changes and refresh the preview line."""
        self._update_preview()

    def _get_base_title(self) -> str:
        """Return the effective base title.

        Falls back to the fetched title if the current field is empty.

        Returns:
            Effective base title string.
        """
        entered = self.base_title_var.get().strip()
        return entered or self.fetched_title

    def _get_start_number(self) -> int:
        """Return a validated start number.

        Invalid or empty values fall back to 1. Minimum value is always 1.

        Returns:
            Validated start number.
        """
        raw = self.start_number_var.get().strip()

        if not raw:
            return 1

        value = int(raw)
        return max(1, value)

    def _update_preview(self) -> None:
        """Refresh the preview line based on current field values."""
        base_title = self._get_base_title()
        start_number = self._get_start_number()

        # Show first + range example
        preview_start = f"{base_title}, Vol. {start_number}"
        preview_next = f"{base_title}, Vol. {start_number + 1}"

        self.preview_var.set(
            f"{preview_start}\n{preview_next}"
        )

    def _on_ok(self) -> None:
        """Store the dialog result and close the dialog."""
        self.result = {
            "base_title": self._get_base_title(),
            "start_number": self._get_start_number(),
        }
        self.destroy()

    def _on_cancel(self) -> None:
        """Cancel the dialog without applying any changes."""
        self.result = None
        self.destroy()

    def _validate_number(self, value: str) -> bool:
        """Allow only empty string or digits (for live typing)."""
        return value == "" or value.isdigit()