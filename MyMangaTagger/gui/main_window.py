# gui/main_window.py

"""
Main application window and GUI manager for MyMangaTagger.

This module defines the MainWindow class, which builds and manages
the application's primary GUI, including file listing, metadata editing,
cover display, and processing controls.
"""

import threading
import code
import tkinter as tk
import ttkbootstrap as tb
from tkinter import filedialog
from tkinterdnd2 import TkinterDnD
from pathlib import Path

import services.constants as constants
from services.config import config_manager
from services.file_io import IOService
from services.logger import log
from services.normalization import Normalizer
from services.templating import FilenameFormatter
from services.cover_manager import CoverManager

from gui.log_viewer import LogViewer
from gui.panels.file_list_panel import FileListPanel
from gui.panels.cover_panel import CoverPanel
from gui.panels.control_panel import ControlPanel
from gui.settings_dialog import SettingsDialog
from gui.url_dialog import UrlDialog
from gui.batch_apply_dialog import BatchApplyDialog

from sources.router import RouterSource

class MainWindow:
    """
    Main application window and GUI manager.

    Args:
        root (TkinterDnD): Root TkinterDnD instance.
        io_service (IOService): Service for CBZ I/O.
        normalizer (Normalizer): Metadata normalization service.
        formatter (FilenameFormatter): Filename formatting helper.
        cover_manager (CoverManager): Handles cover image caching and selection.

    Attributes:
        cbz_list (list[Path]): List of loaded CBZ files.
        current_index (int | None): Index of the selected file.
        metadata (dict[Path, dict[str, str]]): Loaded or edited metadata by file.
    """
    def __init__(
        self,
        root: TkinterDnD,
        io_service: IOService,
        normalizer: Normalizer,
        formatter: FilenameFormatter,
        cover_manager: CoverManager,
    ) -> None:
        self.root = root
        self.root.title(constants.APP_TITLE)
        self.io = io_service
        self.normalizer = normalizer
        self.formatter = formatter
        self.cover = cover_manager

        self.cbz_list: list[Path] = []
        self.current_index: int | None = None
        self.metadata: dict[Path, dict[str, str]] = {}

        # Flags for Process step
        self.rename_enabled = True
        self.move_enabled = True

        # Create a style object
        self.style = tb.Style("darkly")

        # Set default font and size for widgets
        self.style.configure(".", font=constants.DEFAULT_FONT)

        # Make style object accessible through root
        self.root.style = self.style

        self.build_gui()

    @staticmethod
    def consensus_metadata_dict(
        dicts: list[dict], keys: list[str], keep_value: str = constants.KEEP_ORIGINAL
    ) -> dict:
        """
        Return a metadata dict where each key is:
          - the shared value if all dicts have the same value,
          - or `keep_value` if they differ.
        """
        result: dict = {}
        for key in keys:
            values = [d.get(key, "").strip() for d in dicts]
            result[key] = values[0] if len(set(values)) == 1 else keep_value
        return result

    def build_gui(self) -> None:
        """Builds and lays out the entire application UI."""
        # --- Main Paned Window (left/right split) ---
        main_paned = tk.PanedWindow(
            self.root,
            orient=tk.HORIZONTAL,
            bg=self.style.colors.dark,
            bd=0,
            sashwidth=4,
            sashrelief="flat",
            sashpad=2,
        )
        main_paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # --- Left Pane (vertical stack for preview, controls, files) ---
        left_pane = tb.Frame(main_paned, width=constants.LEFT_PANE_MIN_WIDTH)
        left_pane.pack_propagate(False)
        main_paned.add(left_pane, minsize=constants.LEFT_PANE_MIN_WIDTH)

        # --- Right Pane for metadata fields ---
        right_pane = tb.Frame(main_paned)
        main_paned.add(right_pane, minsize=constants.RIGHT_PANE_MIN_WIDTH)

        # --- Right Header: Settings & Log ---
        header = tb.Frame(right_pane)
        header.pack(side=tk.TOP, fill=tk.X, pady=(3,0))
        header_spacer = tb.Frame(header)
        header_spacer.pack(side=tk.LEFT, expand=True, fill=tk.X)
        # Log before Settings as they are added from the right side. End result -> Settings | Log
        tb.Button(header, text="Log", command=self._on_show_log, bootstyle="info-outline"
                  ).pack(side=tk.RIGHT, padx=(0, 10), pady=(10,0))
        tb.Button(header, text="Settings", command=self._on_settings, bootstyle="info-outline"
                  ).pack(side=tk.RIGHT, padx=(0, 10), pady=(10,0))

        # --- Top row: Cover Preview (left) and Controls (right) ---
        top_row = tb.Frame(left_pane)
        top_row.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        # Cover Preview (LabelFrame, fixed width)
        self.cover_panel = CoverPanel(
            top_row,
            style=self.style,
            get_thumbnail=self.cover.get_thumbnail,
            on_drop_cover=self._on_drop_cover_cb,
            width=constants.THUMBNAIL_WIDTH,
            height=constants.THUMBNAIL_HEIGHT,
        )
        self.cover_panel.frame.pack(side=tk.LEFT, padx=(0, 5), fill=tk.Y)

        # Controls (right of cover preview)
        self.control_panel = ControlPanel(
            top_row,
            style=self.style,
            on_fetch=self._on_fetch,
            on_process=self._on_process,
            on_toggle_rename=self._on_toggle_rename,
            on_toggle_move=self._on_toggle_move,
            on_set_cover=self._set_cover_cb,
            on_reset_cover=self._reset_cover_cb,
            get_current_cbz_path=lambda: self.cover_panel.current_path,
        )
        self.control_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # --- File Listbox (fills remaining space in left pane) ---
        self.file_list_panel = FileListPanel(
            left_pane,
            style=self.style,
            on_files_dropped=self._on_files_dropped,
            on_selection=self._on_selection,
            on_open_folder=self._open_folder,
            on_drag_enter=self._on_drag_enter,
            on_drag_leave=self._on_drag_leave,
            on_files_removed=self._on_files_removed
        )
        self.file_list_panel.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=0)

        # Metadata fields
        self.fields: dict[str, tk.Widget] = {}
        self.widget_to_field: dict[tk.Widget, str] = {}
        self.languageiso_var = tk.StringVar(value=constants.DEFAULT_LANGUAGE)
        self.manga_var = tk.StringVar(value=constants.DEFAULT_MANGA)
        self.agerating_var = tk.StringVar(value=constants.DEFAULT_AGERATING)

        # --- Metadata tabs: Basic and People + Additional Fields ---
        notebook = tb.Notebook(right_pane)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=0)
        basic_tab    = tb.Frame(notebook)
        advanced_tab = tb.Frame(notebook)
        notebook.add(basic_tab,    text="Basic Fields")
        notebook.add(advanced_tab, text="People + Additional Fields")

        def make_field(parent: tk.Widget, key: str, *args, **widget_opts) -> tb.Frame:
            """
            Create a labeled input widget bound to a metadata key.

            Can be called in two forms:
              1) make_field(parent, key, widget_cls, **opts)
                 → uses `key` (lowercased) as both storage key and label.

              2) make_field(parent, key, label_text, widget_cls, **opts)
                 → uses `label_text` for display, but still stores under `key`.

            Args:
                parent: container to attach this row to.
                key:    metadata key (will be lowercased for storage).
                *args:  either (widget_cls,) or (label_text, widget_cls).
                **widget_opts: passed directly to widget_cls(...)

            Returns:
                A Frame containing the Label + widget.
            """
            # Determine whether label_text was overridden
            if len(args) == 1:
                widget_cls = args[0]
                label_text = key
            elif len(args) == 2:
                label_text, widget_cls = args
            else:
                raise TypeError(
                    "make_field() expects (parent, key, widget_cls, …) or "
                    "(parent, key, label_text, widget_cls, …)"
                )

            frame = tb.Frame(parent)
            # Display the label
            tb.Label(frame, text=label_text, font=constants.FONT_LABEL_BOLD).pack(anchor=tk.W)

            # Create & pack the actual input widget
            if widget_cls == tb.OptionMenu:
                # OptionMenu requires: parent, variable, first_value, *values[1:], ...options
                option_values = widget_opts.pop('values')
                variable = widget_opts.pop('variable')
                # Defensive: set variable if empty
                if not variable.get() and option_values:
                    variable.set(option_values[0])
                widget = widget_cls(frame, variable, variable.get(), *option_values, **widget_opts)
                widget.pack(fill=tk.X)
                # OptionMenu uses variable trace instead of events
                variable.trace_add("write", lambda *a, w=widget: self.on_field_edit(w))
            else:
                widget = widget_cls(frame, **widget_opts)
                widget.pack(fill=tk.X)
                # Bind edits back into the model
                widget.bind("<KeyRelease>", self.on_field_edit)
                if isinstance(widget, tb.Combobox):
                    widget.bind("<<ComboboxSelected>>", self.on_field_edit)

            # Register under lowercase key
            field_key = key.lower()
            self.fields[field_key] = widget
            self.widget_to_field[widget] = field_key
            return frame

        # Field setup (Basic tab)
        # TITLE
        f = make_field(basic_tab, "Title", tb.Entry)
        f.pack(fill=tk.X, padx=5, pady=(15,4))

        # SERIES + LOCALIZEDSERIES
        row = tb.Frame(basic_tab)
        f = make_field(row, "Series", tb.Entry)
        f.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        f = make_field(row, "LocalizedSeries", "Localized Series", tb.Entry)
        f.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        row.pack(fill=tk.X, pady=4)

        # NUMBER + COUNT + SERIESGROUP
        row = tb.Frame(basic_tab)
        f = make_field(row, "Number", tb.Entry, width=4)
        f.pack(side=tk.LEFT, padx=(0, 10))
        f = make_field(row, "Count", tb.Entry, width=4)
        f.pack(side=tk.LEFT, padx=(0, 10))
        f = make_field(row, "SeriesGroup", "Series Group ( Magazine / Event / Collection )", tb.Entry)
        f.pack(side=tk.LEFT, expand=True, fill=tk.X)
        row.pack(fill=tk.X, padx=5, pady=4)

        # SUMMARY
        f = make_field(basic_tab, "Summary", tk.Text, height=7, wrap="word")
        f.pack(fill=tk.X, padx=5, pady=4)

        # YEAR + MONTH + DAY, and LanguageISO, Manga and AgeRating (dropdowns for the last 3)
        row = tb.Frame(basic_tab)
        for label in ["Year", "Month", "Day"]:
            f = make_field(row, label, tb.Entry, width=6)
            f.pack(side=tk.LEFT, padx=(0,10))

        # LanguageISO dropdown: include blank option at top
        lang_values = [""] + constants.LANGUAGE_DISPLAY
        f = make_field(
            row, "LanguageISO", tb.OptionMenu,
            variable=self.languageiso_var,
            values=lang_values,
        )
        self.fields["languageiso"].configure(width=13, bootstyle="light-outline")
        f.pack(side=tk.LEFT, padx=(0, 10))

        # Manga dropdown: include blank option at top
        f = make_field(
            row, "Manga", tb.OptionMenu,
            variable=self.manga_var,
            values=[""] + constants.MANGA_VALUES,
        )
        self.fields["manga"].configure(width=8, bootstyle="light-outline")
        f.pack(side=tk.LEFT, padx=(0, 10))

        # AgeRating dropdown: include blank option at top
        f = make_field(
            row, "AgeRating", tb.OptionMenu,
            variable=self.agerating_var,
            values=[""] + constants.AGERATING_VALUES,
        )
        self.fields["agerating"].configure(width=16, bootstyle="light-outline")
        f.pack(side=tk.LEFT, padx=(0, 10))
        row.pack(fill=tk.X, padx=5, pady=4)

        # WRITER + IMPRINT
        row = tb.Frame(basic_tab)
        f = make_field(row, "Writer", tb.Entry)
        f.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        f = make_field(row, "Imprint", "Imprint (e.g. Circle)", tb.Entry)
        f.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        row.pack(fill=tk.X, pady=4)

        # PUBLISHER + GENRE
        row = tb.Frame(basic_tab)
        f = make_field(row, "Publisher", tb.Entry)
        f.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        f = make_field(row, "Genre", "Genre (or Parody)", tb.Entry)
        f.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        row.pack(fill=tk.X, pady=4)

        # TAGS
        f = make_field(basic_tab, "Tags", tk.Text, height=5, wrap="word")
        f.pack(fill=tk.X, padx=5, pady=4)

        # WEB
        f = make_field(basic_tab, "Web", tk.Text, height=4, wrap="none")
        f.pack(fill=tk.X, padx=5, pady=4)

        # Advanced tab (People + Additional Fields)
        # Penciller, Inker, Colorist
        row = tb.Frame(advanced_tab)
        for label in ["Penciller", "Inker", "Colorist"]:
            f = make_field(row, label, tb.Entry, width=20)
            f.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        row.pack(fill=tk.X, pady=(15,4))

        # Letterer, CoverArtist
        row = tb.Frame(advanced_tab)
        f = make_field(row, "Letterer", tb.Entry, width=20)
        f.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        f = make_field(row, "CoverArtist", "Cover Artist", tb.Entry, width=20)
        f.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        row.pack(fill=tk.X, pady=4)

        # Editor, Translator
        row = tb.Frame(advanced_tab)
        for label in ["Editor", "Translator"]:
            f = make_field(row, label, tb.Entry, width=20)
            f.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        row.pack(fill=tk.X, pady=4)

        # Characters, Teams
        row = tb.Frame(advanced_tab)
        for label in ["Characters", "Teams"]:
            f = make_field(row, label, tb.Entry)
            f.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        row.pack(fill=tk.X, pady=4)

        # Locations, MainCharacterOrTeam
        row = tb.Frame(advanced_tab)
        f = make_field(row, "Locations", tb.Entry)
        f.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        f = make_field(row, "MainCharacterOrTeam", "Main Character or Team", tb.Entry)
        f.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        row.pack(fill=tk.X, pady=4)

        # AlternateSeries, AlternateNumber, AlternateCount
        row = tb.Frame(advanced_tab)
        for key, label, width in [
            ("AlternateSeries",  "Alternate Series", 40),
            ("AlternateNumber",  "Alternate Number",  4),
            ("AlternateCount",   "Alternate Count",   4),
        ]:
            f = make_field(row, key, label, tb.Entry, width=width)
            f.pack(side=tk.LEFT, padx=5)
        row.pack(fill=tk.X, pady=4)

        # StoryArc + StoryArcNumber
        row = tb.Frame(advanced_tab)
        f = make_field(row, "StoryArc", "Story Arc", tb.Entry, width=40)
        f.pack(side=tk.LEFT, padx=5)
        f = make_field(row, "StoryArcNumber", "Story Arc Number", tb.Entry, width=6)
        f.pack(side=tk.LEFT, padx=5)
        row.pack(fill=tk.X, pady=4)

        # ScanInformation (single-line)
        f = make_field(advanced_tab, "ScanInformation", "Scan Information", tb.Entry)
        f.pack(fill=tk.X, padx=5, pady=4)

        # Notes (5-line text box)
        f = make_field(advanced_tab, "Notes", tk.Text, height=5, wrap="word")
        f.pack(fill=tk.X, padx=5, pady=4)

        # Status bar with two lines and a log alert label
        self.status_var1 = tk.StringVar()
        self.status_var2 = tk.StringVar()
        status_frame = tb.Frame(self.root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        status_lines = tb.Frame(status_frame)
        status_lines.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10,0), pady=2)
        tb.Label(status_lines, textvariable=self.status_var1, anchor="w").pack(fill=tk.X)
        tb.Label(status_lines, textvariable=self.status_var2, anchor="w").pack(fill=tk.X)

        # Log alert indicator (right)
        self.log_alert_label = tb.Label(
            status_frame,
            text="",
            font=constants.DEFAULT_FONT_BOLD,
            foreground="#d9534f",
            cursor="hand2"
        )
        self.log_alert_label.pack(side=tk.RIGHT, padx=(5, 10), pady=2)
        self.log_alert_label.bind("<Button-1>", lambda e: self._on_show_log())

        # Set initial statuses
        self.status_reporter(line1="Program started. Ready.", line2="", level2="NONE")
        self.clear_log_alert()

        # ——— DEBUG: open interactive console on Ctrl+Shift+I ———
        # this will drop you into a REPL where `self` is your MainWindow
        # Use "Ctrl+Z -> Enter" to get back to regular console on Windows
        self.root.bind(
            "<Control-Shift-I>",
            lambda event: threading.Thread(
                target=self._open_console, daemon=True
            ).start()
        )

    def on_field_edit(self, event_or_widget) -> None:
        """
        Handles inline edits to metadata fields and updates the model.

        Args:
            event_or_widget: Either a Tkinter event or a widget.
        """
        sel = self.file_list_panel.listbox.curselection()
        if not sel:
            return

        # Support both call styles (event or widget)
        if hasattr(event_or_widget, 'widget'):
            widget = event_or_widget.widget
        else:
            widget = event_or_widget

        key = self.widget_to_field.get(widget)
        if not key:
            return

        if key == "languageiso":
            if self.languageiso_var.get() == constants.KEEP_ORIGINAL:
                return
            val = self.get_languageiso_code()
        elif key == "manga":
            if self.manga_var.get() == constants.KEEP_ORIGINAL:
                return
            val = self.manga_var.get()
        elif key == "agerating":
            if self.agerating_var.get() == constants.KEEP_ORIGINAL:
                return
            val = self.agerating_var.get()
        elif isinstance(widget, tk.Text):
            val = widget.get("1.0", tk.END).strip()
            if key == "web":
                # Each non-empty line is a URL
                lines = [line.strip() for line in val.splitlines() if line.strip()]
                val = " ".join(lines)
        else:
            val = widget.get()

        for i in sel:
            f = self.cbz_list[i]
            if f not in self.metadata:
                self.metadata[f] = {}
            self.metadata[f][key] = val

    def get_selected_paths(self) -> list[Path]:
        """Return a list of currently selected CBZ file paths."""
        indices = self.file_list_panel.listbox.curselection()
        return [self.cbz_list[i] for i in indices] if indices else []

    def _on_drag_enter(self, _=None) -> None:
        """Highlight file list label when drag enters."""
        self.file_list_panel.empty_list_label.configure(foreground=self.style.colors.info)

    def _on_drag_leave(self, _=None) -> None:
        """Restore file list label appearance when drag leaves."""
        self.file_list_panel.empty_list_label.configure(foreground=self.style.colors.light)

    def _on_files_removed(self, paths: list[Path]) -> None:
        """
        Remove files from the model and update selection according to deletion scope.

        Behavior:
            - If exactly one file was deleted, select the file that now occupies the
              deleted file's previous index (or the last item if the deleted file was
              last in the list).
            - If multiple files were deleted, select the first remaining file.
            - If no files remain, clear all metadata fields and cover.

        Args:
            paths: List of file Paths that were removed from the list.
        """
        if not paths:
            return

        # --- Determine selection target BEFORE mutating self.cbz_list ---
        # Collect original indices (if present) of the soon-to-be-deleted paths
        deleted_indices: list[int] = []
        for p in paths:
            try:
                deleted_indices.append(self.cbz_list.index(p))
            except ValueError:
                # Path not in the list (already removed or inconsistent state); ignore
                pass

        # Decide which index we want to land on after removal:
        # - single deletion: the original index of that one item
        # - multi deletion: sentinel (we'll use 0 later if items remain)
        target_index: int | None
        if len(deleted_indices) == 1:
            target_index = deleted_indices[0]
        else:
            target_index = None  # Will default to 0 if any files remain

        # --- Perform the removals from the model (list + metadata) ---
        for p in paths:
            if p in self.cbz_list:
                self.cbz_list.remove(p)
            if p in self.metadata:
                del self.metadata[p]

        # --- Update UI selection based on the new list state ---
        if self.cbz_list:
            # Resolve target index:
            if target_index is None:
                # Multi-delete: select first item
                resolved_index = 0
            else:
                # Single-delete: clamp to the last valid index (handles "deleted last item")
                resolved_index = min(target_index, len(self.cbz_list) - 1)

            self.current_index = resolved_index
            self.file_list_panel.listbox.select_clear(0, tk.END)
            self.file_list_panel.listbox.select_set(resolved_index)
            # Ensure listbox's active/see states are updated for better UX
            self.file_list_panel.listbox.activate(resolved_index)
            self.file_list_panel.listbox.see(resolved_index)

            # Update the right-hand metadata fields + cover for the new selection
            self._on_selection(resolved_index)
        else:
            # No files left; clear the UI
            self.current_index = None
            self.file_list_panel.listbox.select_clear(0, tk.END)
            self.clear_metadata_fields()
            self.cover_panel.show_cover(None)

        # Status line update
        self.status_reporter(line2=f"Deleted {len(paths)} file(s).", level2="DEBUG")


    def load_metadata_for_files(self, files: list[Path]) -> None:
        """
        Loads ComicInfo.xml metadata for each file in the background and updates status.

        Args:
            files: List of Path objects to load metadata for.
        """
        def task():
            for f in files:
                if f not in self.metadata:
                    file_meta = self.io.extract_comicinfo(f)
                    # Always set these default values if missing from loaded file
                    if "languageiso" not in file_meta or not file_meta["languageiso"]:
                        file_meta["languageiso"] = ""
                    if "manga" not in file_meta or not file_meta["manga"]:
                        file_meta["manga"] = constants.DEFAULT_MANGA
                    if "agerating" not in file_meta or not file_meta["agerating"]:
                        file_meta["agerating"] = constants.DEFAULT_AGERATING

                    self.metadata[f] = file_meta
        threading.Thread(target=task, daemon=True).start()

    def _on_files_dropped(self, paths: list[Path]) -> None:
        """Handle files dropped into the UI and initiate metadata loading."""
        self._on_drag_leave()
        new_files = []
        for p in paths:
            if p not in self.cbz_list:
                self.cbz_list.append(p)
                new_files.append(p)
        if new_files:
            self.file_list_panel.update_list(self.cbz_list)
            self.load_metadata_for_files(new_files)
            self.status_reporter(line2=f"{len(self.cbz_list)} files loaded", level2="DEBUG")
        else:
            self.status_reporter(line2="No new files added (duplicates ignored)", level2="NONE")

    def _open_folder(self) -> None:
        """Open a folder chooser and load all CBZ files within."""
        folder = filedialog.askdirectory()
        if folder:
            loaded = self.io.load_cbz_files(Path(folder))
            self.cbz_list = loaded
            self.file_list_panel.update_list(self.cbz_list)
            self.load_metadata_for_files(self.cbz_list)
            self.status_reporter(line2=f"{len(self.cbz_list)} files loaded", level2="DEBUG")

    def _on_settings(self) -> None:
        """Open the Toplevel-based settings dialog."""
        SettingsDialog(self.root, self.style)

    def _on_show_log(self) -> None:
        """Show or focus the log viewer window."""
        if hasattr(self, 'log_viewer') and self.log_viewer.winfo_exists():
            self.log_viewer.lift()
        else:
            self.log_viewer = LogViewer(self.root, self.style)
        self.clear_log_alert()

    def _on_selection(self, index: int) -> None:
        """
        Handle selection of a file in the listbox. Loads ComicInfo.xml if needed.

        Args:
            index: Index of the selected file in cbz_list.
        """
        self.current_index = index
        sel = self.file_list_panel.listbox.curselection()
        paths = [self.cbz_list[i] for i in sel]
        if not paths:
            return

        # Ensure metadata loaded for each selected file
        # Normally loaded automatically for all files, but background loader could be slow
        metas = []
        for p in paths:
            if p not in self.metadata:
                self.metadata[p] = self.io.extract_comicinfo(p)
            metas.append(self.metadata[p])

        # Single-file vs. multi-file display
        if len(metas) == 1:
            meta = metas[0]
        else:
            # compute consensus across all selected files
            keys = [k.lower() for k in self.io.FIELD_NAMES]
            meta = self.consensus_metadata_dict(metas, keys)

        # LanguageISO dropdown
        lang = meta.get("languageiso", "")
        if lang == constants.KEEP_ORIGINAL:
            self.languageiso_var.set(constants.KEEP_ORIGINAL)
        else:
            self.set_languageiso_by_code(lang)

        # Manga dropdown
        mg = meta.get("manga", "")
        if mg == constants.KEEP_ORIGINAL:
            self.manga_var.set(constants.KEEP_ORIGINAL)
        else:
            self.manga_var.set(mg or constants.DEFAULT_MANGA)

        # AgeRating dropdown
        ar = meta.get("agerating", "")
        if ar == constants.KEEP_ORIGINAL:
            self.agerating_var.set(constants.KEEP_ORIGINAL)
        else:
            self.agerating_var.set(ar or constants.DEFAULT_AGERATING)

        # All other fields (Entry/Text) same as single-file logic
        for key, widget in self.fields.items():
            if key in ("languageiso", "manga", "agerating"):
                continue
            val = meta.get(key, "")
            if key == "web":
                # one URL per line
                collapsed = " ".join(val.split())
                val = "\n".join(collapsed.strip().split())
            if isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END)
                widget.insert("1.0", val)
            else:
                widget.delete(0, tk.END)
                widget.insert(0, val)

        # Show the cover of the first file in the selection
        self.cover_panel.show_cover(paths[0])

    def _on_fetch(self, mode: str) -> None:
        """Start fetching metadata using a single RouterSource.

        Args:
            mode: "Auto" or any available source.
                In "Auto" mode, the router detects which source to use based on the URL.
        """
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            self.status_reporter(line2="[FETCH] No files selected for metadata fetch.", level2="DEBUG")
            return

        # --- Fetch Mode branching: single URL apply vs per-file ---
        fetch_mode = self.control_panel.get_fetch_mode()
        if fetch_mode == constants.FETCH_MODE_SINGLE_APPLY and len(selected_paths) > 1:
            self._on_fetch_single_apply(mode, selected_paths)
            return

        forced = None if mode == "Auto" else mode.lower()

        src = RouterSource(
            self,
            cover_getter=self.cover.get_thumbnail,
            status_reporter=self.status_reporter,
            forced_source=forced,
        )

        mode_label = mode
        self.status_reporter(line1=f"Fetching metadata ({mode_label}) for {len(selected_paths)} file(s)...")

        threading.Thread(target=lambda: self._run_fetch_source(src, selected_paths), daemon=True).start()

    def _run_fetch_source(self, src, paths: list[Path]) -> None:
        """
        Fetch metadata from a given source in the background, then normalize and store results.

        As each file's metadata is fetched, fields in the GUI are updated if that file is currently selected.
        Progress and status updates are sent using the status_reporter method.
        """

        total = len(paths)

        # Start fetching
        results, skipped, cancelled = src.fetch_metadata(paths)

        # Process results
        for path, raw in results.items():
            # Normalize and store metadata
            norm: dict = {}
            for k, v in raw.items():
                if k == 'summary':
                    norm[k] = v.strip()
                else:
                    norm[k] = self.normalizer.normalize_whitespace(v)
            self.metadata[path] = norm

        # After all files are updated, refresh GUI for the current selection
        if self.current_index is not None:
            self.root.after(0, lambda: self._on_selection(self.current_index))

        fetched_count = len(results)
        skipped_count = len(skipped)
        cancelled_count = len(cancelled)
        total_count = len(paths)
        status_parts = []

        if fetched_count:
            status_parts.append(f"Fetched metadata for {fetched_count} file{'s' if fetched_count != 1 else ''}")
        if skipped_count:
            status_parts.append(f"skipped {skipped_count}")
        if cancelled_count:
            status_parts.append(f"cancelled {cancelled_count}")

        if skipped_count == total_count:
            status_msg = "Fetch skipped for all files."
        elif cancelled_count == total_count:
            status_msg = "Fetch cancelled for all files."
        else:
            status_msg = "Fetch complete. " + ", ".join(status_parts) + "."

        # Final update
        self.status_reporter(
            line1="Ready.",
            line2=status_msg,
            level1="NONE",
        )

    def _on_fetch_single_apply(self, mode: str, paths: list[Path]) -> None:
        """Prompt once for a URL, fetch metadata once, and apply it to all selected files.

        After a successful fetch, a second dialog allows the user to confirm or
        override the shared base title, choose the starting number, and preview
        the generated title format before the metadata is applied.

        Auto-numbering uses the current list selection order:
            - Number = start_number..start_number + N - 1
            - Title = "{base_title}, Vol. {Number}"

        Args:
            mode: One of constants.FETCH_MODE_OPTIONS.
            paths: Selected file paths to receive the same fetched metadata.
        """
        # Resolve forced source for the router (None = Auto)
        forced: str | None = None if mode == "Auto" else mode.lower()

        # Build a router (reuses sessions inside source adapters)
        src = RouterSource(
            self,
            cover_getter=self.cover.get_thumbnail,
            status_reporter=self.status_reporter,
            forced_source=forced,
        )

        # Prompt once for the URL; show a compact hint about multi-apply
        dlg = UrlDialog(
            self.root,
            file_name=f"{len(paths)} file(s) selected",
            title="Enter URL (applies to ALL selected files)"
        )
        url = dlg.result
        if not url:
            self.status_reporter(line2="[FETCH] Cancelled fetch for all files.", level2="DEBUG")
            return

        self.status_reporter(
            line1=f"Fetching shared metadata ({mode})...",
            line2=f"URL entered; applying to {len(paths)} file(s) on success.",
            level1="NONE",
            level2="DEBUG",
        )

        def task() -> None:
            # 1) Fetch once (network call off the UI thread)
            raw = src.fetch_from_url(url)

            if not raw:
                self.status_reporter(line2="[FETCH] No metadata returned.", level2="WARN")
                return

            # 2) Normalize fields (Summary trim; whitespace-normalize others)
            norm: dict[str, str] = {}
            for k, v in raw.items():
                if k == "summary":
                    norm[k] = (v or "").strip()
                else:
                    norm[k] = self.normalizer.normalize_whitespace(v)

            fetched_title = norm.get("title", "").strip()
            options = self._prompt_batch_apply_options(
                fetched_title=fetched_title,
                start_number=1,
            )

            if options is None:
                self.status_reporter(
                    line1="Ready.",
                    line2="[FETCH] Cancelled batch apply options.",
                    level1="NONE",
                    level2="DEBUG",
                )
                return

            base_title = str(options["base_title"]).strip() or fetched_title
            start_number = int(options["start_number"])

            # 3) Apply per-file with chosen title base and starting number
            for offset, path in enumerate(paths):
                volume_number = start_number + offset
                md = dict(norm)

                # Auto-number (stored as string for ComicInfo)
                md["number"] = str(volume_number)

                # Title is always based on the chosen batch title
                md["title"] = self._append_volume_to_title(base_title, volume_number)

                self.metadata[path] = md

            # 4) Refresh the right-hand fields if selection is visible
            if self.current_index is not None:
                self.root.after(0, lambda: self._on_selection(self.current_index))

            # 5) Final status
            end_number = start_number + len(paths) - 1
            self.status_reporter(
                line1="Ready.",
                line2=(
                    f"Applied fetched metadata to {len(paths)} file(s) "
                    f"(numbers {start_number}-{end_number})."
                ),
                level1="NONE",
                level2="INFO",
            )

        threading.Thread(target=task, daemon=True).start()

    def _on_process(self) -> None:
        """
        Handles the 'Process' action by starting a background thread to process selected files.
        Ensures the GUI remains responsive by offloading file I/O to a separate thread.
        """
        indices = list(self.file_list_panel.listbox.curselection())
        if not indices:
            self.status_reporter(line2="No files selected to process.", level2="DEBUG")
            return

        # Start background processing thread
        processing_thread = threading.Thread(
            target=lambda: self._process_files_in_background(indices),
            daemon=True
        )
        processing_thread.start()

    def _process_files_in_background(self, indices: list[int]) -> None:
        """
        Processes files in the background (not on the main Tkinter thread). This method performs all
        file I/O and heavy lifting, and schedules GUI updates back to the main thread via `self.root.after`.

        Performance:
            • Uses IOService.update_cbz_metadata() which auto-selects a metadata-only fast path
              when safe (no new cover, no overwrite requested, and no WebP pages).
            • In metadata-only mode, only ComicInfo.xml is replaced.
            • When a cover is provided or WebP pages exist, a streamed rebuild runs. Images are
              written with ZIP_STORED and WebP pages (and WebP cover) are converted to PNG.

        Args:
            indices: List of indices of selected files to process.
        """
        files_to_process = [self.cbz_list[i] for i in indices]
        processed_files = []
        total = len(indices)

        for idx, (i, path) in enumerate(zip(indices, files_to_process), start=1):
            # Send status updates back to the main thread
            self.status_reporter(
                line1=f"Processing {idx}/{total}: {path.name}",
            )

            data = self.metadata.get(path, {})
            custom_cover_path = self.cover.custom_covers.get(path.resolve())
            cover_mode = self.control_panel.get_cover_mode()
            overwrite_existing_cover = (cover_mode == "replace")

            # 1) Write updated ComicInfo.xml and (optionally) inject/replace cover
            #    Uses a smart, streamed writer with WebP→PNG normalization:
            #    - Metadata-only fast path when safe (no new cover, no overwrite, no WebP pages)
            #    - Otherwise streamed rebuild: images ZIP_STORED, ComicInfo ZIP_DEFLATED,
            #      .webp pages (and WebP cover) converted to .png.
            self.io.update_cbz_metadata(
                path,
                data,
                custom_cover_path=custom_cover_path,
                overwrite_existing_cover=overwrite_existing_cover,
                metadata_only=None,  # None = auto (use fast path when safe)
            )

            # Remove custom cover from cache, as the archive is now up-to-date
            self.cover.clear_custom_cover(path.resolve())

            # 2) Rename file if requested
            if self.rename_enabled:
                new_name = self.formatter.format(self.metadata[path], path)
                new_path = self.io.rename_cbz(path, new_name)
                path = new_path
                self.cbz_list[i] = path

            # 3) Move file if requested
            if self.move_enabled:
                out_cfg = config_manager.output_folder
                mode = out_cfg.get("mode", "relative")
                if mode == "static":
                    dest = Path(out_cfg.get("static_path", ""))
                else:
                    dest = path.parent / out_cfg.get("relative_name", "")
                series_name = data.get("series", "") or ""
                if series_name.strip():
                    safe_series = self.normalizer.sanitize_path_component(series_name)
                    dest = dest / safe_series
                new_location = self.io.move_cbz(path, dest)
                path = new_location
                self.cbz_list[i] = path

            processed_files.append(path)

        # Schedule cleanup and final GUI update after all files are processed
        self.root.after(0, lambda: self._processing_done(processed_files))

    def _processing_done(self, processed_files: list[Path]) -> None:
        """
        Finalizes processing after all files are handled. Updates the GUI, removes processed files,
        clears metadata and cover if no files remain, and updates status messages.

        Args:
            processed_files: List of files that were processed.
        """
        # Remove processed files from cbz_list and metadata
        for path in processed_files:
            if path in self.cbz_list:
                self.cbz_list.remove(path)
            if path in self.metadata:
                del self.metadata[path]

        # Update file list and GUI selection
        self.file_list_panel.update_list(self.cbz_list)

        if self.cbz_list:
            self.current_index = 0
            self.file_list_panel.listbox.select_clear(0, tk.END)
            self.file_list_panel.listbox.select_set(0)
            self._on_selection(0)
        else:
            # No files left; clear fields and cover
            self.current_index = None
            self.file_list_panel.listbox.select_clear(0, tk.END)
            self.clear_metadata_fields()
            self.cover_panel.show_cover(None)

        self.status_reporter(
            line1="Ready.",
            line2=f"Processed {len(processed_files)} file(s).",
            level1="NONE",
        )

    def _on_toggle_rename(self, enabled: bool) -> None:
        """Enable or disable the rename step."""
        self.rename_enabled = enabled

    def _on_toggle_move(self, enabled: bool) -> None:
        """Enable or disable the move step."""
        self.move_enabled = enabled

    def _set_cover_cb(self, cbz_path: Path | None, image_path: Path | None = None) -> None:
        """Callback to apply a custom cover and refresh display."""
        if not cbz_path:
            self.status_reporter(line2="Cannot set cover: No manga file selected.", level2="DEBUG")
            return
        if not image_path:
            # Do nothing or prompt for image selection if you want
            return
        self.cover.set_custom_cover(cbz_path, image_path)
        self.cover_panel.show_cover(cbz_path)
        log("DEBUG", f"Added {image_path.name} as cover for {cbz_path.name}")

    def _reset_cover_cb(self, cbz_path: Path | None) -> None:
        """Callback to reset to the original cover."""
        if not cbz_path:
            self.status_reporter(line2="Cannot reset cover: No manga file selected.", level2="DEBUG")
            return
        self.cover.clear_custom_cover(cbz_path)
        self.cover_panel.show_cover(cbz_path)
        log("DEBUG", f"Cover reset for: {cbz_path.name}")

    def _on_drop_cover_cb(self, cbz_path: Path, image_path: Path) -> None:
        """Handle a dropped cover image into the cover panel."""
        self.cover.set_custom_cover(cbz_path, image_path)
        self.cover_panel.show_cover(cbz_path)
        log("DEBUG", f"Added {image_path.name} as cover for {cbz_path.name}")

    def run(self) -> None:
        """Enter the Tkinter main loop."""
        self.root.mainloop()

    def set_status1(self, text: str) -> None:
        """Set the first line of the status bar."""
        self.status_var1.set(text)

    def set_status2(self, text: str) -> None:
        """Set the second line of the status bar."""
        self.status_var2.set(text)

    def clear_status2(self) -> None:
        """Clear the second status line."""
        self.status_var2.set("")

    def status_reporter(
            self,
            line1: str = None,
            line2: str = None,
            progress: float = None,
            level1: str = "INFO",
            level2: str = "INFO",
    ) -> None:
        """
        Thread-safe unified way to update GUI status lines and log messages.

        Args:
            line1 (str, optional): Text for the first status line.
            line2 (str, optional): Text for the second status line.
            progress (float, optional): Progress ratio (0.0–1.0) for a progress bar (future use).
            level1 (str, optional): Log level for line1 ("INFO", "DEBUG", "WARN", "ERROR", "NONE").
            level2 (str, optional): Log level for line2 ("INFO", "DEBUG", "WARN", "ERROR", "NONE").
        """

        def apply() -> None:
            if line1 is not None:
                self.set_status1(line1)
                if level1 != "NONE":
                    log(level1, line1)
            if line2 is not None:
                self.set_status2(line2)
                if level2 != "NONE":
                    log(level2, line2)
            # You may update a progress bar here in the future using the `progress` value.

        self.root.after(0, apply)

    def show_log_alert(self, level: str) -> None:
        """
        Show a visual log alert in the status bar for warnings/errors.

        Args:
            level: Log level, e.g., 'WARN', 'ERROR', 'CRITICAL'
        """
        if level in ("ERROR", "CRITICAL"):
            self.log_alert_label.config(
                text="ERRORS encountered, see log.",
                foreground="#d9534f"
            )
        elif level in ("WARN", "WARNING"):
            self.log_alert_label.config(
                text="WARNINGS encountered, see log.",
                foreground="#f0ad4e"
            )
        else:
            self.log_alert_label.config(text="", foreground="")

    def clear_log_alert(self) -> None:
        """Hide the log alert label."""
        self.log_alert_label.config(text="", foreground="")

    def handle_log_status(self, level: str) -> None:
        """
        Called by logger when a warning/error/critical is logged.
        """
        self.show_log_alert(level)

    def get_languageiso_code(self) -> str:
        """
        Get the 2-letter language code from the LanguageISO dropdown.

        Returns:
            The language code string, or empty string if not mapped.
        """
        return constants.LANGUAGE_CODE_MAP.get(self.languageiso_var.get(), "")

    def set_languageiso_by_code(self, code: str) -> None:
        """
        Set the LanguageISO dropdown using a 2-letter code.

        Args:
            code: 2-letter language code.
        """
        for display in constants.LANGUAGE_DISPLAY:
            if display.startswith(code + " "):
                self.languageiso_var.set(display)
                return
        self.languageiso_var.set(constants.DEFAULT_LANGUAGE)

    def _open_console(self) -> None:
        """
        Launch an interactive Python console in your terminal.

        In this REPL you can type expressions like:
            >>> self.fields
            >>> list(self.metadata.keys())
        """
        console = code.InteractiveConsole(locals={"self": self})
        console.interact()

    def clear_metadata_fields(self) -> None:
        """
        Clear or reset all GUI metadata fields to their default/empty states.
        Handles Text, Entry, and dropdown (Combobox/OptionMenu) widgets.
        """
        for key, widget in self.fields.items():
            if isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END)
            elif isinstance(widget, tk.Entry):
                widget.delete(0, tk.END)
            elif key == "languageiso":
                if self.languageiso_var.get() != constants.KEEP_ORIGINAL:
                    self.languageiso_var.set(constants.DEFAULT_LANGUAGE)
            elif key == "manga":
                if self.manga_var.get() != constants.KEEP_ORIGINAL:
                    self.manga_var.set(constants.DEFAULT_MANGA)
            elif key == "agerating":
                if self.agerating_var.get() != constants.KEEP_ORIGINAL:
                    self.agerating_var.set(constants.DEFAULT_AGERATING)
            else:
                # Extend for other dropdowns as needed
                pass

    def _prompt_batch_apply_options(
        self,
        fetched_title: str,
        start_number: int = 1,
    ) -> dict[str, str | int] | None:
        """Show the batch apply dialog on the Tk main thread and return the result.

        This helper exists because metadata fetching runs on a background thread,
        while Tkinter dialogs must be created on the main GUI thread.

        Args:
            fetched_title: Title fetched from the metadata source.
            start_number: Initial start number to show in the dialog.

        Returns:
            None if the dialog was cancelled, otherwise a dict containing:
                - "base_title": str
                - "start_number": int
        """
        done = threading.Event()
        result_holder: dict[str, dict[str, str | int] | None] = {"result": None}

        def show_dialog() -> None:
            dialog = BatchApplyDialog(
                self.root,
                fetched_title=fetched_title,
                start_number=start_number,
            )
            result_holder["result"] = dialog.result
            done.set()

        self.root.after(0, show_dialog)
        done.wait()
        return result_holder["result"]

    def _append_volume_to_title(self, title: str, num: int) -> str:
        """Return `title` with `, Vol. {num}` suffix.

        Args:
            title: Original title string (can be empty).
            num: Volume number to inject.

        Returns:
            Title string with a single trailing `, Vol. {num}`.
        """
        if not title:
            # If there was no title, provide at least "Vol. X"
            return f"Vol. {num}"

        return f"{title}, Vol. {num}"
