# gui/panels/cover_panel.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES
from pathlib import Path
from PIL import Image, ImageTk
from typing import Callable, Optional

from services.cover_manager import CoverManager
from services.logger import log

DEFAULT_COVER_PATH = Path(__file__).parent.parent.parent / "assets/default_cover.png"

class CoverPanel:
    """
    Displays the current cover image and provides UI for cover selection/reset.

    Args:
        parent: Parent Tkinter container.
        style (tb.Style): The style object for widget theming and styling.
        get_thumbnail: Returns a PIL.Image.Image thumbnail for a CBZ file.
        on_drop_cover: Called as on_drop_cover(cbz_path, image_path).
        width: Width of the preview image.
        height: Height of the preview image.

    Attributes:
        frame: Main container frame.
        canvas: Canvas displaying the cover image.
        current_path: The current CBZ file being shown.
    """
    def __init__(
        self,
        parent: tk.Widget,
        style: tb.Style,
        get_thumbnail: Callable[[Path], Image.Image],
        on_drop_cover: Callable[[Path, Path], None],
        width: int = 160,
        height: int = 240,
    ) -> None:
        # Store callbacks and sizing
        self.parent = parent
        self.style = style
        self.get_thumbnail = get_thumbnail
        self.on_drop_cover = on_drop_cover
        self.width = width
        self.height = height
        self.current_path: Optional[Path] = None

        # Main frame for this panel
        self.frame = tb.Frame(parent)
        self.frame.config(width=self.width, height=self.height)
        self.frame.pack_propagate(False)

        # Canvas to draw the cover image
        self.canvas = tk.Canvas(self.frame, width=self.width, height=self.height)
        self.canvas.pack()

        # Enable drag-and-drop on the canvas
        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self._on_cover_drop)

        # Load the default cover image once
        default_img = Image.open(DEFAULT_COVER_PATH)
        default_img = default_img.resize((self.width, self.height), Image.LANCZOS)
        self.default_photo = ImageTk.PhotoImage(default_img)
        self.default_img = default_img

        # Initially show the default image
        self.show_cover(None)

    def pack(self, **kwargs) -> None:
        """
        Pack this panel into its parent.

        Keyword args are passed to tb.Frame.pack().
        """
        self.frame.pack(**kwargs)

    def show_cover(self, cbz_path: Optional[Path]) -> None:
        """
        Display the cover for the given CBZ path.
        If cbz_path is None, show the default cover.

        Args:
            cbz_path: Path to the CBZ file or None.
        """
        self.current_path = cbz_path
        self.canvas.delete("all")

        if not cbz_path:
            # No file selected: use default
            img = self.default_img
        else:
            try:
                # Get the custom thumbnail
                img = self.get_thumbnail(cbz_path.resolve())
            except Exception:
                log("ERROR", f"CoverPanel error loading cover for {cbz_path}", exc_info=True)
                img = self.default_img

        # Fit and center image, then update canvas
        display_img = CoverManager.render_for_canvas(img, self.width, self.height)
        photo = ImageTk.PhotoImage(display_img)
        self.canvas.create_image(
            self.width // 2,
            self.height // 2,
            anchor=tk.CENTER,
            image=photo
        )
        # Prevent garbage collection
        self.canvas.image = photo

    def _on_cover_drop(self, event: tk.Event) -> None:
        """
        Handle drag-and-drop of an image file onto the canvas.

        Args:
            event: The Tkinter DND event containing file data.
        """
        files = self.parent.tk.splitlist(event.data)  # type: ignore[attr-defined]
        if not files:
            return
        dropped = Path(files[0].strip("{}"))
        if not dropped.is_file():
            return

        # Only allow certain image extensions
        if dropped.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
            messagebox.showwarning(
                "Unsupported File",
                "Only image files (.jpg, .jpeg, .png, .gif, .webp) can be used as cover."
            )
            return

        if not self.current_path:
            messagebox.showwarning(
                "No Manga Selected",
                "Please select a manga first to set its cover."
            )
            return

        # Apply the dropped cover and refresh display
        self.on_drop_cover(self.current_path, dropped)
        self.show_cover(self.current_path)
