"""
Entry point for the MyMangaTagger application.

This module initializes core services and launches the GUI
"""

from tkinterdnd2 import TkinterDnD
from functools import partial
from ttkbootstrap.utility import enable_high_dpi_awareness

import services.constants as constants
from services.logger import set_debug, set_log_alert_callback
from services.config import config_manager
from services.file_io import IOService
from services.normalization import Normalizer
from services.templating import FilenameFormatter
from services.cover_manager import CoverManager

from gui.main_window import MainWindow


def main() -> None:
    """
    Initialize application and start the main GUI loop.

    Sets up a drag-and-drop root window, configures logging,
    initializes I/O, normalization, filename-formatting and cover
    services, then launches the main application window.
    """

    # Set Windows DPI Awareness
    enable_high_dpi_awareness()

    # Initialize the TkinterDnD-enabled root window.
    root = TkinterDnD.Tk()

    # Set window size and position (centered)
    root.withdraw()  # Hide while setting up
    app_width = constants.APP_WIDTH
    app_height = constants.APP_HEIGHT
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width // 2) - (app_width // 2)
    y = (screen_height // 2) - (app_height // 2)
    root.geometry(f"{app_width}x{app_height}+{x}+{y}")
    root.minsize(constants.APP_MIN_WIDTH, constants.APP_MIN_HEIGHT)
    root.deiconify()  # Show window after geometry is set

    # Configure logging based on DEBUG_LOGGING setting.
    set_debug(config_manager.debug_logging)

    # Initialize core services.
    io_service = IOService()
    normalizer = Normalizer()
    formatter = FilenameFormatter()
    cover_manager = CoverManager()

    # Create and run the main application window.
    app = MainWindow(
        root=root,
        io_service=io_service,
        normalizer=normalizer,
        formatter=formatter,
        cover_manager=cover_manager,
    )

    # Register log alert callback to display non-intrusive GUI warnings/errors.
    set_log_alert_callback(partial(app.handle_log_status))

    app.run()
    return

if __name__ == "__main__":
    main()
