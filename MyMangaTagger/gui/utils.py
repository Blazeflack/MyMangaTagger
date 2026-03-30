# gui/utils.py

"""Utility functions for GUI dialogs and windows in MyMangaTagger."""

import tkinter as tk

def center_window_on_parent(
    parent: tk.Tk | tk.Toplevel,
    window: tk.Toplevel,
    width: int,
    height: int,
) -> None:
    """Center a Toplevel or dialog window over its parent window.

    Args:
        parent: The parent tk.Tk or tk.Toplevel instance.
        window: The tk.Toplevel or tk.Widget to position.
        width: Width of the window in pixels.
        height: Height of the window in pixels.
    """
    # Ensure the parent's layout measurements are up-to-date.
    parent.update_idletasks()

    # Get parent's absolute screen position and size.
    parent_x = parent.winfo_rootx()
    parent_y = parent.winfo_rooty()
    parent_width = parent.winfo_width()
    parent_height = parent.winfo_height()

    # Calculate center position for the child window.
    x_position = parent_x + (parent_width - width) // 2
    y_position = parent_y + (parent_height - height) // 2

    # Apply the geometry to position the window.
    window.geometry(f"{width}x{height}+{x_position}+{y_position}")
