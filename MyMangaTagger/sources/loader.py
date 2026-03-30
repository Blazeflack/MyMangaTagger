# sources/loader.py

"""Auto-import all MetadataSource subclasses found in the sources/ package."""

import importlib
import pkgutil
from pathlib import Path


def load_all_sources() -> None:
    """Import every module in the sources/ package so subclasses self-register."""
    package_dir = Path(__file__).parent
    package_name = __package__ or "sources"

    for _, module_name, _ in pkgutil.iter_modules([str(package_dir)]):
        if module_name in ("base", "loader", "router"):
            continue
        try:
            importlib.import_module(f"{package_name}.{module_name}")
        except Exception as exc:
            from services.logger import log
            log("WARN", f"[Loader] Could not load source module '{module_name}': {exc}")