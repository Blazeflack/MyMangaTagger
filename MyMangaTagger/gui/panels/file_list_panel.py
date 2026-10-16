# gui/panels/file_list_panel.py

"""
File list panel for MyMangaTagger GUI.

This module defines FileListPanel, which encapsulates the drag-and-drop
listbox for CBZ files, placeholder hints, file selection/removal logic,
and a context menu for copying the immediate parent folder name.
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
        self.listbox.bind("<Button-3>", self._show_context_menu)

        # Context menu for copying file-related information.
        # Keep the clicked path separate from the current selection.
        self._context_path: Optional[Path] = None
        self.context_menu = tk.Menu(self.listbox, tearoff=False)
        self.context_menu.add_command(
            label="Copy Parent Folder Name",
            command=self._copy_parent_folder_name,
        )

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

    def _show_context_menu(self, event: tk.Event) -> str:
        """Show the context menu for the CBZ file under the mouse.

        The menu is only displayed when right-clicking a visible file
        row. Existing file selections are preserved.

        Args:
            event: Right-click event containing mouse coordinates.

        Returns:
            "break" to prevent further handling of the event.
        """
        if not self.paths:
            return "break"

        # Determine which file was right-clicked.
        index = self.listbox.nearest(event.y)

        if not 0 <= index < len(self.paths):
            return "break"

        # Ignore clicks in empty space below the file entries.
        bounds = self.listbox.bbox(index)
        if bounds is None:
            return "break"

        _, top, _, height = bounds
        if not top <= event.y < top + height:
            return "break"

        # Remember the clicked file without changing the selection.
        self._context_path = self.paths[index]

        # Display the context menu at the mouse position.
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

        return "break"

    def _copy_parent_folder_name(self) -> None:
        """Copy the clicked CBZ file's immediate parent folder name.

        Uses the original file path stored in the file list rather than
        the displayed filename or current selection.
        """
        if self._context_path is None:
            return

        # Extract only the immediate parent directory name.
        folder_name = self._context_path.parent.name

        if not folder_name:
            return

        # Copy the folder name to the system clipboard.
        self.listbox.clipboard_clear()
        self.listbox.clipboard_append(folder_name)
        self.listbox.update_idletasks()

        log("DEBUG", f"Copied parent folder name: {folder_name}")

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
