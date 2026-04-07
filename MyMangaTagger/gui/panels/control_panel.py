# gui/panels/control_panel.py

import tkinter as tk
from tkinter import filedialog
import ttkbootstrap as tb
from pathlib import Path
from typing import Any, Callable

import services.constants as constants

class ControlPanel:
    """
    Panel providing all user controls for cover management and batch file operations.

    Args:
        parent: Parent Tkinter container.
        style (tb.Style): The style object for widget theming and styling.
        on_fetch: Callback taking a string ("Auto", or available source name) to select fetch source.
        on_process: Callback when 'Process Selected Files' is pressed.
        on_toggle_rename: Callback when renaming is toggled.
        on_toggle_move: Callback when moving is toggled.
        on_set_cover: Callback to set a custom cover.
        on_reset_cover: Callback to reset to default cover.
        get_current_cbz_path: Function to retrieve the currently selected CBZ path.
    """

    def __init__(
        self,
        parent: tk.Widget,
        style: tb.Style,
        on_fetch: Callable[[str], None],
        on_process: Callable[[], None],
        on_toggle_rename: Callable[[bool], None],
        on_toggle_move: Callable[[bool], None],
        on_set_cover: Callable[[Path | None, Path | None], None],
        on_reset_cover: Callable[[Path | None], None],
        get_current_cbz_path: Callable[[], Path | None],
    ) -> None:
        """Initialize the control panel UI and hook up callbacks.

        Args:
            parent: Parent Tkinter container.
            style: The ttkbootstrap style object for widget theming and styling.
            on_fetch: Callback for the "Fetch" button; receives selected source
                as "Auto" or any of available sources
            on_process: Callback when "Process Selected Files" is pressed.
            on_toggle_rename: Callback when renaming is toggled.
            on_toggle_move: Callback when moving is toggled.
            on_set_cover: Callback to set a custom cover.
            on_reset_cover: Callback to reset to default cover.
            get_current_cbz_path: Function to retrieve the currently selected CBZ path.
        """
        self.frame = tb.Frame(parent)
        self.style = style

        # --- Cover Controls Section ---
        cover_controls = tb.LabelFrame(self.frame, text="Cover Controls")
        cover_controls.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(0, 5))
        # Inner frame to handle padding (ttkbootstrap no longer supports padding on LabelFrame)
        inner_cover = tb.Frame(cover_controls, padding=5)
        inner_cover.pack(fill=tk.BOTH, expand=True)

        btn_row = tb.Frame(inner_cover)
        btn_row.pack(fill=tk.X)

        def on_new_cover() -> None:
            """Handler for selecting a new cover image."""
            cbz_path = get_current_cbz_path()
            if not cbz_path:
                on_set_cover(None, None)  # Delegate status display to MainWindow
                return
            file_path = filedialog.askopenfilename(
                filetypes=[("Image files", "*.jpg *.jpeg *.png *.gif *.webp")]
            )
            if file_path:
                on_set_cover(cbz_path, Path(file_path))

        def on_reset_cover_btn() -> None:
            """Handler for resetting the cover to default."""
            cbz_path = get_current_cbz_path()
            on_reset_cover(cbz_path)  # Handles None in MainWindow now

        tb.Button(btn_row, text="New Cover", command=on_new_cover).pack(side=tk.LEFT)
        tb.Button(btn_row, text="Reset Cover", command=on_reset_cover_btn).pack(side=tk.LEFT, padx=(10,0))

        tb.Label(inner_cover, text="When setting custom cover:").pack(anchor=tk.W, pady=(10, 2))
        self.cover_mode_var = tk.StringVar(value="add")
        radio_row = tb.Frame(inner_cover)
        radio_row.pack(anchor=tk.W)
        tb.Radiobutton(radio_row, text="Add (Keep Original)",
                        variable=self.cover_mode_var, value="add").pack(side=tk.LEFT)
        tb.Radiobutton(radio_row, text="Replace",
                        variable=self.cover_mode_var, value="replace").pack(side=tk.LEFT, padx=(10,0))

        # Spacer pushes the metadata section to the bottom
        spacer = tb.Frame(self.frame)
        spacer.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # --- Metadata & Files Section ---
        metadata_frame = tb.LabelFrame(self.frame, text="Metadata & Files")
        metadata_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(5, 0))
        inner_metadata = tb.Frame(metadata_frame, padding=5)
        inner_metadata.pack(fill=tk.BOTH, expand=True)

        # Row for fetch MODE (non-persistent; defaults to Per-file each launch)
        mode_row = tb.Frame(inner_metadata)
        mode_row.pack(fill=tk.X, pady=(0, 8))

        self.fetch_mode_var = tk.StringVar(
            value=constants.FETCH_MODE_OPTIONS[0][0]  # "Per-file"
        )
        tb.Label(mode_row, text="Mode:").pack(side=tk.LEFT, padx=(0, 5))
        mode_menu = tb.OptionMenu(
            mode_row,
            self.fetch_mode_var,
            self.fetch_mode_var.get(),
            *[label for label, _ in constants.FETCH_MODE_OPTIONS],
        )
        mode_menu.configure(width=18, bootstyle="light-outline")
        mode_menu.pack(side=tk.LEFT)

        # Row for fetch controls (source selector + button)
        fetch_row = tb.Frame(inner_metadata)
        fetch_row.pack(fill=tk.X, pady=(0, 20))

        from sources.base import MetadataSource
        from sources.loader import load_all_sources
        load_all_sources()

        self.source_var = tk.StringVar(value="Auto")
        sources = ["Auto"] + MetadataSource.get_source_display_names()

        tb.Label(fetch_row, text="Source:").pack(side=tk.LEFT, padx=(0, 5))
        source_menu = tb.OptionMenu(fetch_row, self.source_var, self.source_var.get(), *sources)
        source_menu.configure(width=6, bootstyle="light-outline")
        source_menu.pack(side=tk.LEFT)

        tb.Button(fetch_row, text="Fetch", command=lambda: on_fetch(self.source_var.get())).pack(
            side=tk.LEFT, padx=(10, 0)
        )

        # Row for rename/move options
        options_row = tb.Frame(inner_metadata)
        options_row.pack(fill=tk.X, pady=5)
        self.rename_var = tk.BooleanVar(value=True)
        self.move_var = tk.BooleanVar(value=True)
        tb.Checkbutton(
            options_row, text="Rename Files", variable=self.rename_var,
            command=lambda: on_toggle_rename(self.rename_var.get())
        ).pack(side=tk.LEFT)
        tb.Checkbutton(
            options_row, text="Move Files", variable=self.move_var,
            command=lambda: on_toggle_move(self.move_var.get())
        ).pack(side=tk.LEFT, padx=(10,0))

        # Process Selected Files button
        tb.Button(inner_metadata, text="Process Selected Files", command=on_process).pack(
            side=tk.LEFT
        )

    def pack(self, **kwargs: Any) -> None:
        """
        Pack the control panel frame into its parent widget.

        Args:
            **kwargs: Keyword arguments forwarded to tkinter's pack().
        """
        self.frame.pack(**kwargs)

    def get_cover_mode(self) -> str:
        """
        Get the current cover mode setting.

        Returns:
            The cover mode, either "add" or "replace".
        """
        return self.cover_mode_var.get()

    def get_selected_source(self) -> str:
        """Return the currently selected metadata source.

        Returns:
            str: "Auto" or any available source name.
        """
        return self.source_var.get()

    def get_fetch_mode(self) -> str:
        """Return the canonical fetch mode value selected in the UI.

        Returns:
            str: One of constants.FETCH_MODE_PER_FILE or constants.FETCH_MODE_SINGLE_APPLY.
        """
        label = self.fetch_mode_var.get()
        label_to_val = {lbl: val for (lbl, val) in constants.FETCH_MODE_OPTIONS}
        return label_to_val.get(label, constants.FETCH_MODE_PER_FILE)
