# templating.py

"""
Module for formatting CBZ filenames based on a user-defined template and metadata.

This module provides the `FilenameFormatter` class, which replaces tokens in a template
(`{TITLE}`, `{WRITER}`, `{SERIESGROUP}`, `{GENRE}`, `{SERIES}`)
with metadata values, cleans up redundant characters and spaces, sanitizes the result for
filesystem safety, and appends a `.cbz` extension.
"""
import re
from pathlib import Path
from typing import Dict

from services.config import config_manager
from services.normalization import Normalizer


class FilenameFormatter:
    """
    Formats filenames based on a template and metadata.
    Always fetches the template (and any limits) live from config.
    """

    def __init__(self) -> None:
        """
        Initialize a FilenameFormatter.

        Args:

        """
        self.normalizer: Normalizer = Normalizer()

    def format(
        self,
        metadata: Dict[str, str],
        cbz_path: Path,
        template_override: str | None = None,
        max_writers_override: int | None = None,
        max_genres_override: int | None = None,
    ) -> str:
        """
        Generate a sanitized filename for a CBZ based on metadata and template.

        Args:
            metadata: Mapping of lowercased ComicInfo fields.
            cbz_path: Original CBZ file path.
            template_override: Optional template to use instead of the saved config value.
            max_writers_override: Optional override for the writer collapse limit.
            max_genres_override: Optional override for the genre collapse limit.

        Returns:
            Sanitized filename ending with '.cbz'.
        """
        # Normalize writer field using configured or overridden limit.
        writer_raw: str = metadata.get("writer", "")
        writer: str = self.normalizer.normalize_writer_field(
            writer_raw,
            max_writers=max_writers_override,
        )

        # Normalize genre field using configured or overridden limit.
        genres_raw: str = metadata.get("genre", "")
        genre: str = self.normalizer.normalize_genre_field(
            genres_raw,
            max_genres=max_genres_override,
        )

        # Title token (fallback to filename stem if missing).
        raw_title_from_metadata = metadata.get("title")
        if raw_title_from_metadata:
            # Use title from metadata as-is (only normalize whitespace).
            title = self.normalizer.normalize_whitespace(raw_title_from_metadata)
        else:
            # Use filename stem with smart title-casing.
            raw_title = cbz_path.stem
            title_cased = self.normalizer.smart_title_case(raw_title)
            title = self.normalizer.normalize_whitespace(title_cased)

        # Build token map.
        tokens: Dict[str, str] = {
            "TITLE": title,
            "WRITER": writer,
            "SERIESGROUP": self.normalizer.normalize_whitespace(metadata.get("seriesgroup", "")),
            "GENRE": genre,
            "SERIES": self.normalizer.normalize_whitespace(metadata.get("series", "")),
        }

        # Substitute tokens in template.
        def substitute(match: re.Match) -> str:
            key: str = match.group(1).upper()
            return tokens.get(key, "")

        # Use override template when provided, otherwise use saved config.
        template = template_override
        if template is None:
            template = config_manager.filename_template or str(
                config_manager.get_default("FILENAME_TEMPLATE", "{TITLE}")
            )

        filename: str = re.sub(r"\{(\w+)\}", substitute, template)

        # Remove empty parentheses/brackets and collapse multiple spaces.
        filename = re.sub(r"\(\s*\)", "", filename)
        filename = re.sub(r"\[\s*\]", "", filename)
        filename = re.sub(r"\s{2,}", " ", filename).strip()

        # Sanitize for filesystem safety.
        filename = self.normalizer.sanitize_path_component(filename)

        # Append .cbz suffix.
        return f"{filename}.cbz"
