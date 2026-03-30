# gui/settings_dialog.py

"""Settings dialog window for the MyMangaTagger application.

This module defines a SettingsDialog class that presents a modal dialog
for viewing and editing user-configurable application settings, including
logging options, output folder preferences, and filename templating.
"""

import tkinter as tk
import ttkbootstrap as tb
from tkinter import filedialog
from pathlib import Path
from typing import Dict

from gui.utils import center_window_on_parent

import services.constants as constants
from services.logger import set_debug
from services.config import config_manager
from services.templating import FilenameFormatter


class SettingsDialog(tk.Toplevel):
    """A modal dialog for configuring application settings.

    Presents controls for:
        - Enabling debug logging
        - Choosing an output folder (static or relative)
        - Defining filename template and preview

    Attributes:
        formatter: Service used for filename formatting
        template_field: StringVar holding the filename template.
        max_writers_field: StringVar holding the max writers limit.
        max_genres_field: StringVar holding the max writers limit.
        output_mode: StringVar for output folder mode ("static" or "relative").
        static_path: StringVar for absolute output folder path.
        relative_name: StringVar for folder name relative to input.
        debug_var: BooleanVar for debug logging toggle.
        preview_var: StringVar for live filename preview text.
    """

    def __init__(self, parent: tk.Tk | tk.Toplevel, style: tb.Style) -> None:
        """Initialize and display the settings dialog.

        Args:
            parent: The parent window over which this dialog is modal.
            style (tb.Style): The style object for widget theming and styling.
        """
        super().__init__(parent)
        self.style = style
        self.title(constants.SETTINGS_TITLE)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center this dialog over its parent window.
        center_window_on_parent(
            parent,
            self,
            constants.SETTINGS_WIDTH,
            constants.SETTINGS_HEIGHT
        )

        # --- State variables ---
        self.formatter = FilenameFormatter()
        self.template_field = tk.StringVar(value=config_manager.filename_template)
        self.max_writers_field = tk.StringVar(value=str(config_manager.max_filename_writers))
        self.max_genres_field = tk.StringVar(value=str(config_manager.max_filename_genres))
        self.output_mode = tk.StringVar(value=config_manager.output_folder.get("mode", "relative"))
        self.static_path = tk.StringVar(value=config_manager.output_folder.get("static_path", ""))
        self.relative_name = tk.StringVar(value=config_manager.output_folder.get("relative_name", "Processed"))
        self.debug_var = tk.BooleanVar(value=config_manager.debug_logging)

        # Build the UI and initialize preview.
        self._build_ui()
        self._update_filename_preview()

        # Keyboard and focus bindings.
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind_all("<Control-s>", lambda e: self._on_save())
        self.lift()
        self.after(100, lambda: (self.focus_force(), self.grab_set()))
        self.wait_window()

    def _build_ui(self) -> None:
        """Construct and layout all widgets in the dialog."""
        # --- Logging section ---
        debug_frame = tb.LabelFrame(self, text="Logging")
        debug_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        inner_debug = tb.Frame(debug_frame, padding=10)
        inner_debug.pack(fill=tk.BOTH, expand=True)

        tb.Checkbutton(
            inner_debug,
            text="Enable more extensive logging in terminal/file",
            variable=self.debug_var
        ).pack(anchor=tk.W)

        # --- Output Folder section ---
        output_frame = tb.LabelFrame(self, text="Output Folder")
        output_frame.pack(fill=tk.X, padx=10)
        inner_output = tb.Frame(output_frame, padding=10)
        inner_output.pack(fill=tk.BOTH, expand=True)

        # Mode selection: static vs relative
        tb.Radiobutton(
            inner_output,
            text="Static folder (absolute)",
            variable=self.output_mode,
            value="static",
            command=self._on_mode_change
        ).pack(anchor=tk.W)
        tb.Radiobutton(
            inner_output,
            text="Relative to input file",
            variable=self.output_mode,
            value="relative",
            command=self._on_mode_change
        ).pack(anchor=tk.W, pady=5)

        # Static path entry and browse button
        self.static_label = tb.Label(inner_output, text="Static path:")
        self.static_label.pack(anchor=tk.W, pady=(5, 0))
        static_path_row = tb.Frame(inner_output)
        static_path_row.pack(fill=tk.X, pady=(0,5))
        self.static_entry = tb.Entry(static_path_row, textvariable=self.static_path)
        self.static_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.static_browse = tb.Button(
            static_path_row, text="Browse", command=self._choose_folder
        )
        self.static_browse.pack(side=tk.LEFT, padx=(5, 0))

        # Relative folder name entry
        self.relative_label = tb.Label(inner_output, text="Relative folder name:")
        self.relative_label.pack(anchor=tk.W, pady=(5, 0))
        self.relative_entry = tb.Entry(inner_output, textvariable=self.relative_name)
        self.relative_entry.pack(fill=tk.X, pady=(0, 5))

        # --- Filename Format section ---
        filename_frame = tb.LabelFrame(self, text="Filename Format")
        filename_frame.pack(fill=tk.X, padx=10, pady=10)
        inner_filename = tb.Frame(filename_frame, padding=10)
        inner_filename.pack(fill=tk.BOTH, expand=True)

        # Available tokens description row
        token_and_limit_row = tb.Frame(inner_filename)
        token_and_limit_row.pack(fill=tk.X)

        # Tokens label (left)
        tb.Label(
            token_and_limit_row,
            text=(
                "Available tokens:\n"
                "{TITLE}, {WRITER}, {IMPRINT}, {IMPRINT_WRITER},\n"
                "{GENRE}, {SERIESGROUP}, {SERIES}"
            ),
            foreground=self.style.colors.light,
            font=constants.DEFAULT_FONT_ITALIC,
            justify="left",
        ).pack(side=tk.LEFT, anchor="w")

        # Limits column (right, vertical stack with grid for perfect alignment)
        limits_col = tb.Frame(token_and_limit_row)
        limits_col.pack(side=tk.RIGHT, anchor="ne", padx=(10, 0), fill=tk.Y)

        # Max writers (row 0)
        tb.Label(
            limits_col,
            text="Max writers before using 'Various Artists':"
        ).grid(row=0, column=0, sticky="e", padx=(0, 5), pady=(0, 3))
        tb.Entry(
            limits_col,
            textvariable=self.max_writers_field,
            width=3
        ).grid(row=0, column=1, sticky="w", pady=(0, 3))

        # Max genres (row 1)
        tb.Label(
            limits_col,
            text="Max genres before using 'Various Genres':"
        ).grid(row=1, column=0, sticky="e", padx=(0, 5))
        tb.Entry(
            limits_col,
            textvariable=self.max_genres_field,
            width=3
        ).grid(row=1, column=1, sticky="w")

        # Template entry and reset button
        entry_row = tb.Frame(inner_filename)
        entry_row.pack(fill=tk.X, pady=10)
        tb.Entry(entry_row, textvariable=self.template_field).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        tb.Button(entry_row, text="Reset", command=self._reset_filename_template).pack(
            side=tk.LEFT, padx=(5, 0)
        )
        # Update preview whenever the template changes
        self.template_field.trace_add("write", lambda *_: self._update_filename_preview())

        # Preview label for formatted filename
        tb.Label(
            inner_filename,
            text="Preview:",
            font=constants.DEFAULT_FONT_BOLD
        ).pack(anchor=tk.W, pady=(0, 5))
        self.preview_var = tk.StringVar(value="")
        self.preview_label = tb.Label(
            inner_filename,
            textvariable=self.preview_var,
            foreground=self.style.colors.info,
            font=constants.DEFAULT_FONT,
            wraplength=560
        )
        self.preview_label.pack(anchor=tk.W)

        # --- Save and Cancel buttons ---
        btns = tb.Frame(self)
        btns.pack(pady=10)
        tb.Button(btns, text="Save", command=self._on_save).pack(side=tk.LEFT, padx=5)
        tb.Button(btns, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=5)

        # Initialize widget states based on current mode
        self._on_mode_change()

    def _on_save(self) -> None:
        """Persist user settings to config and close the dialog."""
        config_manager.set("DEBUG_LOGGING", self.debug_var.get())
        config_manager.set(
            "OUTPUT_FOLDER",
            {
                "mode": self.output_mode.get(),
                "static_path": self.static_path.get().strip(),
                "relative_name": self.relative_name.get().strip(),
            }
        )
        config_manager.set("FILENAME_TEMPLATE", self.template_field.get().strip())
        try:
            max_w = max(0, int(self.max_writers_field.get().strip()))
        except ValueError:
            max_w = int(config_manager.get_default("MAX_FILENAME_WRITERS", 2))
        config_manager.set("MAX_FILENAME_WRITERS", max_w)
        try:
            max_g = max(0, int(self.max_genres_field.get().strip()))
        except ValueError:
            max_g = int(config_manager.get_default("MAX_FILENAME_GENRES", 2))
        config_manager.set("MAX_FILENAME_GENRES", max_g)

        config_manager.save()
        set_debug(self.debug_var.get())

        self.unbind_all("<Control-s>")
        self.destroy()

    def _choose_folder(self) -> None:
        """Open a folder selection dialog and update the static path."""
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.static_path.set(folder)

    def _reset_filename_template(self) -> None:
        """Reset the filename template field to the default value."""
        default_template = str(config_manager.get_default("FILENAME_TEMPLATE", ""))
        self.template_field.set(default_template)

    def _update_filename_preview(self) -> None:
        """Generate and display a live preview of the filename template."""
        example_metadata: Dict[str, str] = {
            "title": "Funny Title",
            "writer": "Awesome Author",
            "imprint": "Crazy Circle",
            "seriesgroup": "Comical Magazine",
            "genre": "Frieren",
            "series": "Succubus Tales",
        }

        try:
            preview = self.formatter.format(example_metadata, Path("Example.cbz"))
        except Exception:
            preview = "Invalid template"
        self.preview_var.set(preview or "—")

    def _on_mode_change(self) -> None:
        """Enable or disable output folder fields based on the selected mode."""
        mode = self.output_mode.get()

        self.static_label.configure(foreground=self.style.colors.fg if mode=="static" else "#555555")
        self.static_entry.configure(state="normal" if mode == "static" else "disabled")
        self.static_browse.configure(state="normal" if mode == "static" else "disabled")

        self.relative_label.configure(foreground=self.style.colors.fg if mode=="relative" else "#555555")
        self.relative_entry.configure(state="normal" if mode == "relative" else "disabled")
