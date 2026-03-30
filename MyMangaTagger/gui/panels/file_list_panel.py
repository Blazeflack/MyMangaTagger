# gui/panels/file_list_panel.py

"""
File list panel for MyMangaTagger GUI.

This module defines FileListPanel, which encapsulates the drag-and-drop
listbox for CBZ files, placeholder hints, and file selection/removal logic.
"""

import tkinter as tk
import ttkbootstrap as tb
from tkinterdnd2 import DND_FILES
from pathlib import Path
from typing import Callable, List, Optional, Any

import services.constants as constants
from services.logger import log

class FileListPanel:
    """
    Encapsulates the file list UI: drag-and-drop Listbox with placeholder,
    folder loading, selection events, and deletion.

    Args:
        parent: Parent Tkinter container.
        style (tb.Style): The style object for widget theming and styling.
        on_files_dropped: Callback(paths: List[Path]) when files are dropped.
        on_selection: Callback(index: int) when an item is selected.
        on_open_folder: Callback() to open folder dialog.
        on_drag_enter: Callback() when drag enters list area.
        on_drag_leave: Callback() when drag leaves list area.
        on_files_removed: Callback(paths: List[Path]) when files are removed.
    """

    def __init__(
        self,
        parent: tk.Widget,
        style: tb.Style,
        on_files_dropped: Callable[[List[Path]], None],
        on_selection: Callable[[int], None],
        on_open_folder: Callable[[], None],
        on_drag_enter: Callable[[], None],
        on_drag_leave: Callable[[], None],
        on_files_removed: Callable[[List[Path]], None],
    ) -> None:
        self.frame = tb.Frame(parent)
        self.style = style
        self.on_files_dropped = on_files_dropped
        self.on_selection = on_selection
        self.on_open_folder = on_open_folder
        self.on_drag_enter = on_drag_enter
        self.on_drag_leave = on_drag_leave
        self.on_files_removed = on_files_removed
        self.paths: List[Path] = []

        # Horizontal and vertical scrollbars
        self.hscrollbar = tb.Scrollbar(self.frame, orient="horizontal")
        self.hscrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.vscrollbar = tb.Scrollbar(self.frame, orient="vertical")
        self.vscrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Container for listbox and placeholder label
        self.list_container = tb.Frame(self.frame)
        self.list_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Listbox setup
        self.listbox = tk.Listbox(
            self.list_container,
            width=60,
            selectmode=tk.EXTENDED,
            exportselection=False,
            yscrollcommand=self.vscrollbar.set,
            xscrollcommand=self.hscrollbar.set,
            highlightthickness=0
        )
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.vscrollbar.config(command=self.listbox.yview)
        self.hscrollbar.config(command=self.listbox.xview)

        # Placeholder label shown when no files are loaded
        self.empty_list_label = tb.Label(
            self.list_container,
            text=constants.FILELIST_DROP_LABEL,
            font=constants.FONT_LARGE_LABEL,
            background=self.style.colors.dark,
            foreground=self.style.colors.light,
        )
        self.empty_list_label.place(relx=0.5, rely=0.5, anchor="center")
        self.empty_list_label.configure(cursor="hand2")

        # Bind drag-and-drop and click events
        for widget in (self.empty_list_label, self.listbox):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind('<<Drop>>', self._handle_drop)
            widget.dnd_bind('<<DropEnter>>', lambda e: self.on_drag_enter())
            widget.dnd_bind('<<DropLeave>>', lambda e: self.on_drag_leave())
        self.empty_list_label.bind('<Enter>', lambda e: self.on_drag_enter())
        self.empty_list_label.bind('<Leave>', lambda e: self.on_drag_leave())
        self.empty_list_label.bind("<Button-1>", lambda e: self.on_open_folder())
        self.listbox.bind("<<ListboxSelect>>", self._handle_select)
        self.listbox.bind("<Delete>", self.delete_selected_files)
        self.listbox.bind("<Control-a>", self.select_all_files)
        self.listbox.bind("<Control-A>", self.select_all_files)

        # Initialize display
        self.update_list(self.paths)

    def _handle_drop(self, event: tk.Event) -> None:
        """
        Accept dropped .cbz/.zip files (renaming .zip to .cbz), and directories
        (adding contained files). Calls on_files_dropped with the valid paths.
        """
        raw = self.frame.tk.splitlist(event.data)
        valid: List[Path] = []
        for p in raw:
            path = Path(p.strip("{}")).expanduser()
            if path.is_dir():
                # Add all .cbz and .zip files within directory
                for file in path.glob("*.cbz"):
                    valid.append(file)
                for file in path.glob("*.zip"):
                    cbz = file.with_suffix(".cbz")
                    try:
                        file.rename(cbz)
                        valid.append(cbz)
                    except Exception:
                        log("ERROR", f"Unable to rename {file} to .cbz", exc_info=True)
            elif path.suffix.lower() == ".zip":
                cbz = path.with_suffix(".cbz")
                try:
                    path.rename(cbz)
                    valid.append(cbz)
                except Exception:
                    log("ERROR", f"Unable to rename {path} to .cbz", exc_info=True)
            elif path.suffix.lower() == ".cbz":
                valid.append(path)
        if valid:
            self.on_files_dropped(valid)

    def _handle_select(self, event: tk.Event) -> None:
        """
        Handle Listbox selection event and call on_selection with first index.
        """
        sel = self.listbox.curselection()
        if sel:
            self.on_selection(sel[0])

    def pack(self, **kwargs: Any) -> None:
        """
        Pack the internal frame into its parent.

        Args:
            **kwargs: Keyword arguments forwarded to tb.Frame.pack().
        """
        self.frame.pack(**kwargs)

    def select_all_files(self, event: Optional[tk.Event] = None) -> str:
        """
        Select all files in the listbox and trigger the on_selection callback.

        Returns:
            "break" to prevent the default Tk binding.
        """
        # select everything
        self.listbox.select_set(0, tk.END)

        # fire on_selection callback with the first selected index
        selected = self.listbox.curselection()
        if selected:
            self.on_selection(selected[0])

        return "break"

    def update_list(self, paths: List[Path]) -> None:
        """
        Refresh the Listbox display with the given CBZ paths or show placeholder.

        Args:
            paths: List of Path objects to display.
        """
        self.paths = list(paths)
        self.listbox.delete(0, tk.END)

        if self.paths:
            self.empty_list_label.place_forget()
            for p in self.paths:
                self.listbox.insert(tk.END, p.name)
        else:
            self.empty_list_label.place(relx=0.5, rely=0.5, anchor="center")

    def delete_selected_files(self, event: Optional[tk.Event] = None) -> None:
        """
        Remove selected files from the list and notify via on_files_removed.

        Args:
            event: Optional Tk event triggering deletion.
        """
        selected_indices = list(self.listbox.curselection())
        if not selected_indices:
            return

        removed = [self.paths[i] for i in selected_indices]
        # Remove in reverse order to maintain indices
        for idx in reversed(selected_indices):
            del self.paths[idx]
        self.update_list(self.paths)
        self.on_files_removed(removed)
