# gui/url_dialog.py

"""URL entry dialog for the MyMangaTagger application.

This module defines UrlDialog, a modal dialog that prompts the user
to enter or paste a URL for a given file. It supports drag-and-drop
of URLs and can auto-submit when the URL matches known source patterns.
"""

import tkinter as tk
import ttkbootstrap as tb
from tkinterdnd2 import DND_TEXT
from typing import Any
from PIL import Image, ImageTk

from services.cover_manager import CoverManager
import services.constants as constants
from gui.utils import center_window_on_parent

class UrlDialog(tk.Toplevel):
    """
    Modal dialog for entering a URL associated with a file, optionally displaying a cover image.

    Args:
        parent: The parent Tkinter widget.
        file_name: The name of the file for which the URL is requested.
        cover_image: A PIL.Image.Image object to display as the file's cover, or None.
        title: Optional custom window title.

    Attributes:
        entry: The text entry widget for the URL.
        result: The dialog outcome (URL string, SKIP constant, or None).
        cover_canvas: The Tkinter Canvas displaying the cover image.
    """

    SKIP: str = "__SKIP__"

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        file_name: str = "",
        cover_image: Image.Image | None = None,
        title: str | None = None,
    ) -> None:
        """
        Initialize the URL dialog window.

        Args:
            parent: The parent Tkinter widget.
            file_name: The name of the file for which the URL is requested.
            cover_image: The PIL.Image.Image to display as a cover preview, or None.
            title: Optional custom window title.
        """
        super().__init__(parent)

        # Set location off-screen and hide immediately while setting up
        # This is an attempt to prevent "creation in top-left and snap to center"
        self.geometry("1x1+10000+10000")
        self.withdraw()
        self.resizable(False, False)
        self.style = getattr(parent, "style", tb.Style.get_instance())
        self.file_name = file_name
        if title:
            self.title(title)

        # Center the dialog over its parent.
        center_window_on_parent(
            parent,
            self,
            constants.URL_DIALOG_WIDTH,
            constants.URL_DIALOG_HEIGHT
        )

        self.transient(parent)
        self.grab_set()

        # --- Main horizontal container (left: fields/buttons, right: cover) ---
        main_row = tk.Frame(self)
        main_row.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # --- Left: Prompt labels, entry, buttons ---
        left_col = tk.Frame(main_row)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tb.Label(
            left_col,
            text="Enter URL for:",
            font=constants.DEFAULT_FONT_BOLD
        ).pack(anchor=tk.W, pady=(10, 5))
        tb.Label(
            left_col,
            text=self.file_name,
            wraplength=600,
            foreground=self.style.colors.info if self.style else None,
        ).pack(anchor=tk.W)

        self.entry = tb.Entry(left_col, width=55)
        self.entry.pack(fill=tk.X, pady=10)
        self.entry.bind("<Return>", lambda e: self._on_ok())
        self.entry.bind("<<Paste>>", self._try_autosubmit)

        btn_frame = tb.Frame(left_col)
        btn_frame.pack(pady=10)
        tb.Button(btn_frame, text="OK", command=self._on_ok).pack(side=tk.LEFT, padx=5)
        tb.Button(btn_frame, text="Skip File", command=self._on_skip).pack(side=tk.LEFT, padx=5)
        tb.Button(btn_frame, text="Cancel All", command=self._on_cancel).pack(side=tk.LEFT, padx=5)

        # --- Right: Cover Canvas ---
        right_col = tk.Frame(main_row)
        right_col.pack(side=tk.LEFT, fill=tk.Y, padx=(24, 0))  # space between left and cover

        # Cover Canvas (same size as before)
        self.cover_canvas = tk.Canvas(right_col, width=160, height=240)
        self.cover_canvas.pack()
        self._cover_photo = None
        self._show_cover(cover_image)

        # Enable drag-and-drop of text (URLs).
        self.drop_target_register(DND_TEXT)
        self.dnd_bind('<<Drop>>', self._on_drop)

        # Placeholder for dialog result
        self.result = None

        # Show dialog now that everything is set up
        self.update_idletasks()
        self.deiconify()

        # Block until dialog is closed
        self.wait_window()

    def _show_cover(self, img: Image.Image | None) -> None:
        """
        Display a PIL Image on the canvas. If None, shows a fallback.

        Args:
            img: A PIL.Image.Image to display as the cover, or None for fallback.
        """
        self.cover_canvas.delete("all")
        if img:
            img_for_canvas = CoverManager.render_for_canvas(
                img,
                160,
                240,
            )
            self._cover_photo = ImageTk.PhotoImage(img_for_canvas)
            self.cover_canvas.create_image(0, 0, anchor=tk.NW, image=self._cover_photo)
        else:
            self.cover_canvas.create_rectangle(0, 0, 160, 240, fill="#ddd")
            self.cover_canvas.create_text(85, 127, text="No cover", fill="#888")

    def _on_skip(self) -> None:
        """Handle 'Skip File': set result to SKIP constant and close."""
        self.result = self.SKIP
        self.destroy()

    def _on_cancel(self) -> None:
        """Handle 'Cancel All': set result to None and close."""
        self.result = None
        self.destroy()

    def _on_ok(self) -> None:
        """Handle 'OK': capture the entered URL and close."""
        self.result = self.entry.get().strip()
        self.destroy()

    def _on_drop(self, event: Any) -> None:
        """Handle drag-and-drop of URL text into the entry field.

        Args:
            event: The drag-and-drop event containing the text.
        """
        url = event.data.strip()
        self.entry.delete(0, tk.END)
        self.entry.insert(0, url)
        # Attempt auto-submit shortly after drop
        self._try_autosubmit()

    def _try_autosubmit(self, event=None) -> None:
        """Schedule auto-submit after paste or drop events."""
        # Delay to ensure the entry widget content is updated
        self.after(50, self._check_and_submit)

    def _check_and_submit(self) -> None:
        """Auto-submit if the URL matches a registered source pattern."""
        from sources.base import MetadataSource
        url = self.entry.get().strip()
        if MetadataSource.detect_from_url(url):
            self.result = url
            self.destroy()
