# gui/panels/control_panel.py

import tkinter as tk
from tkinter import filedialog
import ttkbootstrap as tb
from pathlib import Path
from typing import Any, Callable

import services.constants as constants


class CoverActionsPanel:
    """
    Panel providing cover-specific actions.

    This panel is intended to sit inside the shared selected-file/cover area
    next to the cover preview. It does not draw its own LabelFrame, so the
    cover preview and controls can visually belong to the same compact group.

    Args:
        parent: Parent Tkinter container.
        style: The ttkbootstrap style object for widget theming and styling.
        on_set_cover: Callback to set a custom cover.
        on_reset_cover: Callback to reset to the original cover.
        get_current_cbz_path: Function to retrieve the currently selected CBZ path.

    Attributes:
        frame: Main container frame.
        cover_mode_var: Current custom cover mode, either "add" or "replace".
    """

    def __init__(
        self,
        parent: tk.Widget,
        style: tb.Style,
        on_set_cover: Callable[[Path | None, Path | None], None],
        on_reset_cover: Callable[[Path | None], None],
        get_current_cbz_path: Callable[[], Path | None],
    ) -> None:
        """Initialize the cover actions panel UI and hook up callbacks.

        Args:
            parent: Parent Tkinter container.
            style: The ttkbootstrap style object for widget theming and styling.
            on_set_cover: Callback to set a custom cover.
            on_reset_cover: Callback to reset to the original cover.
            get_current_cbz_path: Function to retrieve the currently selected CBZ path.
        """
        self.frame = tb.Frame(parent)
        self.style = style

        def on_new_cover() -> None:
            """Select a new cover image for the currently selected CBZ file."""
            cbz_path = get_current_cbz_path()
            if not cbz_path:
                on_set_cover(None, None)
                return

            file_path = filedialog.askopenfilename(
                filetypes=[("Image files", "*.jpg *.jpeg *.png *.gif *.webp")]
            )
            if file_path:
                on_set_cover(cbz_path, Path(file_path))

        def on_reset_cover_btn() -> None:
            """Reset the currently selected CBZ file to its original cover."""
            cbz_path = get_current_cbz_path()
            on_reset_cover(cbz_path)

        tb.Label(
            self.frame,
            text="Cover Controls",
            font=constants.FONT_LABEL_BOLD,
        ).pack(anchor=tk.W, pady=(0, 8))

        # Stack buttons vertically to keep the cover area compact in width.
        tb.Button(
            self.frame,
            text="New Cover",
            command=on_new_cover,
            width=16,
        ).pack(anchor=tk.W, fill=tk.X, pady=(0, 6))

        tb.Button(
            self.frame,
            text="Reset Cover",
            command=on_reset_cover_btn,
            width=16,
        ).pack(anchor=tk.W, fill=tk.X, pady=(0, 18))

        tb.Label(
            self.frame,
            text="Custom cover mode:",
        ).pack(anchor=tk.W, pady=(0, 4))

        self.cover_mode_var = tk.StringVar(value="add")

        # Stack radio buttons vertically to avoid wasting horizontal space.
        tb.Radiobutton(
            self.frame,
            text="Add (Keep Original)",
            variable=self.cover_mode_var,
            value="add",
        ).pack(anchor=tk.W, pady=(0, 3))

        tb.Radiobutton(
            self.frame,
            text="Replace",
            variable=self.cover_mode_var,
            value="replace",
        ).pack(anchor=tk.W)

    def pack(self, **kwargs: Any) -> None:
        """Pack the panel frame into its parent widget.

        Args:
            **kwargs: Keyword arguments forwarded to tkinter's pack().
        """
        self.frame.pack(**kwargs)

    def get_cover_mode(self) -> str:
        """Return the selected custom cover handling mode.

        Returns:
            The cover mode, either "add" or "replace".
        """
        return self.cover_mode_var.get()


class MetadataActionsPanel:
    """
    Panel providing metadata fetch, augmentation, and file processing actions.

    Contains source selection, fetch mode selection, metadata fetch action,
    volume metadata augmentation, rename/move toggles, and the processing
    action. The internal grid uses two columns so the action buttons line up
    on the right side.

    Args:
        parent: Parent Tkinter container.
        style: The ttkbootstrap style object for widget theming and styling.
        on_fetch: Callback taking a string ("Auto" or available source name).
        on_augment: Callback when "Augment Metadata" is pressed.
        on_process: Callback when "Process Selected Files" is pressed.
        on_toggle_rename: Callback when renaming is toggled.
        on_toggle_move: Callback when moving is toggled.

    Attributes:
        frame: Main container frame.
        fetch_mode_var: Human-friendly fetch mode label shown in the UI.
        source_var: Currently selected metadata source.
        rename_var: Whether file renaming is enabled.
        move_var: Whether file moving is enabled.
    """

    def __init__(
        self,
        parent: tk.Widget,
        style: tb.Style,
        on_fetch: Callable[[str], None],
        on_augment: Callable[[], None],
        on_process: Callable[[], None],
        on_toggle_rename: Callable[[bool], None],
        on_toggle_move: Callable[[bool], None],
    ) -> None:
        """Initialize the metadata actions panel UI and hook up callbacks.

        Args:
            parent: Parent Tkinter container.
            style: The ttkbootstrap style object for widget theming and styling.
            on_fetch: Callback for the "Fetch Metadata" button; receives selected
                source as "Auto" or any available source.
            on_augment: Callback for the "Augment Metadata" button.
            on_process: Callback when "Process Selected Files" is pressed.
            on_toggle_rename: Callback when renaming is toggled.
            on_toggle_move: Callback when moving is toggled.
        """
        self.frame = tb.Frame(parent)
        self.style = style

        metadata_frame = tb.LabelFrame(self.frame, text="Metadata & Files")
        metadata_frame.pack(side=tk.TOP, fill=tk.X, padx=0, pady=(0, 5))

        # Inner frame handles padding because ttkbootstrap LabelFrame padding
        # behavior differs between versions.
        inner_metadata = tb.Frame(metadata_frame, padding=8)
        inner_metadata.pack(fill=tk.BOTH, expand=True)

        # Two balanced columns make the controls read as rows of label/action
        # pairs, while keeping the action buttons aligned on the right.
        inner_metadata.columnconfigure(0, weight=1)
        inner_metadata.columnconfigure(1, weight=0, minsize=155)

        from sources.base import MetadataSource
        from sources.loader import load_all_sources
        load_all_sources()

        self.source_var = tk.StringVar(value="Auto")
        sources = ["Auto"] + MetadataSource.get_source_display_names()

        self.fetch_mode_var = tk.StringVar(
            value=constants.FETCH_MODE_OPTIONS[0][0]
        )

        # Row 1: Source selector on the left, fetch action on the right.
        source_cell = tb.Frame(inner_metadata)
        source_cell.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 15))
        source_cell.columnconfigure(1, weight=1)

        tb.Label(source_cell, text="Source:").grid(row=0, column=0, sticky="w", padx=(0, 5))

        source_menu = tb.OptionMenu(
            source_cell,
            self.source_var,
            self.source_var.get(),
            *sources,
        )
        source_menu.configure(width=12, bootstyle="light-outline")
        source_menu.grid(row=0, column=1, sticky="ew")

        tb.Button(
            inner_metadata,
            text="Fetch Metadata",
            command=lambda: on_fetch(self.source_var.get()),
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 10))

        # Row 2: Fetch mode selector on the left, augmentation action on the right.
        mode_cell = tb.Frame(inner_metadata)
        mode_cell.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(0, 15))
        mode_cell.columnconfigure(1, weight=1)

        tb.Label(mode_cell, text="Mode:").grid(row=0, column=0, sticky="w", padx=(0, 5))

        mode_menu = tb.OptionMenu(
            mode_cell,
            self.fetch_mode_var,
            self.fetch_mode_var.get(),
            *[label for label, _ in constants.FETCH_MODE_OPTIONS],
        )
        mode_menu.configure(width=12, bootstyle="light-outline")
        mode_menu.grid(row=0, column=1, sticky="ew")

        tb.Button(
            inner_metadata,
            text="Augment Metadata",
            command=on_augment,
        ).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 10))

        # Row 3: Rename/move options on the left, process action on the right.
        options_cell = tb.Frame(inner_metadata)
        options_cell.grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(0, 0))

        self.rename_var = tk.BooleanVar(value=True)
        self.move_var = tk.BooleanVar(value=True)

        tb.Checkbutton(
            options_cell,
            text="Rename Files",
            variable=self.rename_var,
            command=lambda: on_toggle_rename(self.rename_var.get()),
        ).pack(side=tk.LEFT, padx=(0, 12))

        tb.Checkbutton(
            options_cell,
            text="Move Files",
            variable=self.move_var,
            command=lambda: on_toggle_move(self.move_var.get()),
        ).pack(side=tk.LEFT)

        tb.Button(
            inner_metadata,
            text="Process Selected Files",
            command=on_process,
        ).grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(2, 0))

    def pack(self, **kwargs: Any) -> None:
        """Pack the panel frame into its parent widget.

        Args:
            **kwargs: Keyword arguments forwarded to tkinter's pack().
        """
        self.frame.pack(**kwargs)

    def get_selected_source(self) -> str:
        """Return the currently selected metadata source.

        Returns:
            "Auto" or any available source name.
        """
        return self.source_var.get()

    def get_fetch_mode(self) -> str:
        """Return the canonical fetch mode value selected in the UI.

        Returns:
            One of constants.FETCH_MODE_PER_FILE or
            constants.FETCH_MODE_SINGLE_APPLY.
        """
        label = self.fetch_mode_var.get()
        label_to_val = {lbl: val for (lbl, val) in constants.FETCH_MODE_OPTIONS}
        return label_to_val.get(label, constants.FETCH_MODE_PER_FILE)
