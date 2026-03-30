# services/config.py

import json
import threading
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Optional, TypedDict

from services.logger import log

# Path to the JSON file storing user overrides
CONFIG_PATH = Path(__file__).parent.parent / "settings.json"

# Immutable default settings
DEFAULTS = MappingProxyType({
    "DEBUG_LOGGING": False,
    "OUTPUT_FOLDER": MappingProxyType({
        "mode": "relative",           # "relative" or "static"
        "relative_name": "Processed", # relative-mode subfolder name
        "static_path": ""             # absolute path if static
    }),
    "FILENAME_TEMPLATE": "[{IMPRINT_WRITER}] {TITLE} ({SERIESGROUP}) ({GENRE})",
    "MAX_FILENAME_WRITERS": 2,
    "MAX_FILENAME_GENRES": 2,
})

def deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge `updates` into `base` and return base."""
    for k, v in updates.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base

class ConfigManager:
    """Thread-safe configuration manager for application settings.

    The manager owns the in-memory runtime configuration, merges user overrides
    onto immutable defaults, and exposes a small public API for reading and
    writing settings without leaking the underlying dictionary structure.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        """Initialize the config manager.

        Args:
            path: Optional override path for the JSON settings file.
        """
        self._lock = threading.Lock()
        self.path = path or CONFIG_PATH
        self._defaults: Dict[str, Any] = deep_merge({}, dict(DEFAULTS))
        self._config: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        """Load settings from disk and merge them onto defaults.

        Returns:
            The merged configuration dictionary.
        """
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return deep_merge(deep_merge({}, self._defaults), data)
            except Exception:
                log("ERROR", "Error loading custom settings. Falling back to default.")
                return deep_merge({}, self._defaults)
        return deep_merge({}, self._defaults)

    def save(self) -> None:
        """Persist current configuration to disk."""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as file_handle:
                json.dump(self._config, file_handle, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a config value.

        Args:
            key: Config key to read.
            default: Fallback value if the key is missing.

        Returns:
            The stored value or the provided fallback.
        """
        return self._config.get(key, default)

    def get_default(self, key: str, default: Any = None) -> Any:
        """Retrieve a default config value.

        Args:
            key: Config key to read from the immutable defaults.
            default: Fallback value if the key is missing.

        Returns:
            The default value or the provided fallback.
        """
        return self._defaults.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Update a config value in memory.

        Args:
            key: Config key to update.
            value: New value to store.
        """
        with self._lock:
            self._config[key] = value

    @property
    def debug_logging(self) -> bool:
        """Return whether debug logging is enabled."""
        return bool(self._config["DEBUG_LOGGING"])

    @property
    def output_folder(self) -> Dict[str, Any]:
        """Return output folder settings."""
        return dict(self._config["OUTPUT_FOLDER"])

    @property
    def filename_template(self) -> str:
        """Return the active filename template."""
        return str(self._config["FILENAME_TEMPLATE"])

    @property
    def max_filename_writers(self) -> int:
        """Return the configured writer limit for filename generation."""
        return int(self._config["MAX_FILENAME_WRITERS"])

    @property
    def max_filename_genres(self) -> int:
        """Return the configured genre limit for filename generation."""
        return int(self._config["MAX_FILENAME_GENRES"])

# Singleton instance for easy import
config_manager = ConfigManager()
