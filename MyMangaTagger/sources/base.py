"""
Base class and shared exceptions for MyMangaTagger metadata sources.

Defines:
  - SourceFetchError: Exception raised by source clients on fetch failure.
  - MetadataSource: Abstract base class for all metadata source adapters,
    providing the URL-prompt/fetch/skip/cancel loop and the plugin registry.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, ClassVar, Dict, List, Optional

import pyperclip
from PIL import Image

from gui.url_dialog import UrlDialog
from services.logger import log


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SourceFetchError(Exception):
    """Raised by a source client when a fetch or parse operation fails.

    Catching this exception at the adapter layer (``_fetch_from_url``)
    allows sources to distinguish expected fetch failures from unexpected
    programming errors.
    """


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class MetadataSource(ABC):
    """Abstract base for all metadata source adapters.

    Provides the standard URL-prompt/fetch/skip/cancel loop used by every
    source, as well as the class-level plugin registry that enables
    drop-in source discovery via ``sources/loader.py``.

    Subclasses must define:
        - ``source_key`` (str): Unique registry identifier.
        - ``source_name`` (str): Human-friendly source name used in the GUI.
        - ``url_patterns`` (list[str]): Substrings used for URL auto-detection.
        - ``_fetch_from_url(url)`` (method): Performs the actual fetch.

    Args:
        parent: Main GUI controller (must expose ``root`` for dialogs).
        title: Window title for the URL entry dialog.
        cover_getter: Optional callable ``(Path) -> PIL.Image.Image | None``
            used to display a cover preview in the URL dialog.
        status_reporter: Optional callable for sending status/progress
            messages to the GUI.

    Class attributes:
        SKIP: Sentinel value returned by UrlDialog when the user skips a file.
        _registry: Class-level dict mapping source_key → subclass.
    """

    SKIP = "__SKIP__"

    _registry: ClassVar[dict[str, type["MetadataSource"]]] = {}
    source_key: ClassVar[str] = ""
    source_name: ClassVar[str] = ""
    url_patterns: ClassVar[list[str]] = []

    # ------------------------------------------------------------------
    # Plugin registry
    # ------------------------------------------------------------------

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        key = getattr(cls, "source_key", "")
        if key:
            MetadataSource._registry[key] = cls

    @classmethod
    def detect_from_url(cls, url: str) -> Optional[str]:
        """Return the source_key of the first source matching the URL.

        Args:
            url: URL string to inspect.

        Returns:
            Matching source key, or ``None`` if no pattern matches.
        """
        url_lower = url.lower()
        for key, source_cls in cls._registry.items():
            for pattern in source_cls.url_patterns:
                if pattern in url_lower:
                    return key
        return None

    @classmethod
    def registered_sources(cls) -> dict[str, type["MetadataSource"]]:
        """Return a shallow copy of the source registry.

        Returns:
            Dict mapping source_key strings to MetadataSource subclasses.
        """
        return dict(cls._registry)

    @classmethod
    def get_source_display_names(cls) -> list[str]:
        """Return all registered source display names sorted by source key.

        Returns:
            List of human-friendly source names for use in the GUI.
        """
        display_names: list[str] = []
        for key in sorted(cls._registry):
            source_cls = cls._registry[key]
            display_names.append(source_cls.source_name or key)
        return display_names

    @classmethod
    def get_source_key_from_name(cls, source_name: str) -> Optional[str]:
        """Return the source key matching a display name.

        Args:
            source_name: Human-friendly source name shown in the GUI.

        Returns:
            Matching source key, or None if no source uses that name.
        """
        for key, source_cls in cls._registry.items():
            if source_cls.source_name == source_name:
                return key
        return None

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(
        self,
        parent: Any,
        title: str = "",
        cover_getter: Optional[Callable[[Path], Optional[Image.Image]]] = None,
        status_reporter: Optional[Callable[..., None]] = None,
    ) -> None:
        self.parent          = parent
        self.dialog_title    = title
        self.cover_getter    = cover_getter
        self.status_reporter = status_reporter

    # ------------------------------------------------------------------
    # Public fetch loop
    # ------------------------------------------------------------------

    def fetch_metadata(
        self,
        paths: List[Path],
    ) -> tuple[Dict[Path, Dict[str, str]], list[Path], list[Path]]:
        """Prompt for URLs and fetch metadata for a list of files.

        For each path the file stem is copied to the clipboard, a URL
        dialog is shown, and ``_fetch_from_url`` is called on success.
        The user may skip individual files or cancel all remaining fetches.

        Args:
            paths: File paths to process, in order.

        Returns:
            Three-tuple:

            - ``results``: ``{Path: metadata_dict}`` for each successful fetch.
            - ``skipped``: Paths explicitly skipped by the user.
            - ``canceled``: Paths not reached because the user canceled.
        """
        results:   Dict[Path, Dict[str, str]] = {}
        skipped:   list[Path] = []
        cancelled: list[Path] = []
        total = len(paths)

        for idx, path in enumerate(paths, start=1):
            if self.status_reporter:
                self.status_reporter(
                    line1=f"({idx}/{total}) Fetching metadata for {path.name}",
                    level1="DEBUG",
                )

            # Copy stem to clipboard for quick search
            try:
                pyperclip.copy(path.stem)
            except Exception:
                pass

            # Optionally fetch cover for dialog preview
            cover_img = None
            if self.cover_getter is not None:
                try:
                    cover_img = self.cover_getter(path)
                except Exception:
                    pass

            dlg = UrlDialog(
                self.parent.root,
                file_name=path.name,
                cover_image=cover_img,
                title=self.dialog_title,
            )
            url = dlg.result

            if not url:
                # User canceled — mark all remaining paths as canceled
                remaining = paths[idx - 1:]
                cancelled.extend(remaining)
                for p in remaining:
                    log("DEBUG", f"Cancelled fetching for {p.name}")
                break

            if url == UrlDialog.SKIP:
                if self.status_reporter:
                    self.status_reporter(
                        line2=f"Skipped fetching for {path.name}",
                        level2="DEBUG",
                    )
                skipped.append(path)
                continue

            meta = self._fetch_from_url(url)
            if meta:
                results[path] = meta
                if self.status_reporter:
                    self.status_reporter(
                        line2=f"({idx}/{total}) Fetched metadata for {path.name}",
                        level2="INFO",
                    )

        return results, skipped, cancelled

    def fetch_from_url(self, url: str) -> Dict[str, str]:
        """Public wrapper around ``_fetch_from_url``.

        Allows callers outside the source class to trigger a single-URL
        fetch without accessing the protected method directly.

        Args:
            url: URL to fetch metadata from.

        Returns:
            Metadata dict, or empty dict on failure.
        """
        return self._fetch_from_url(url)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def _fetch_from_url(self, url: str) -> Dict[str, str]:
        """Fetch and return metadata for a single URL.

        Implementations should catch ``SourceFetchError`` for expected
        failures and log them at WARN level. Unexpected exceptions should
        be logged at ERROR level. Always return ``{}`` on failure rather
        than raising.

        Args:
            url: URL to fetch metadata from.

        Returns:
            Dict of metadata fields, or ``{}`` on failure.
        """
        raise NotImplementedError