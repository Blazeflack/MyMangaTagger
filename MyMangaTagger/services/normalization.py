# services/normalization.py

"""
Module for text normalization utilities:
- Whitespace collapsing
- XML-safe text sanitization
- Smart title-casing
- Writer field normalization (limiting number of authors)
- Filesystem path component sanitization
"""
import re
from typing import Optional

from services.config import config_manager
from services.constants import GENRE_REPLACEMENTS


class Normalizer:
    """
    Provides text normalization utilities:
    - Whitespace collapsing
    - XML text sanitization
    - Smart title-casing
    - Writer field normalization (limiting number of authors)
    - Filesystem path component sanitization
    """

    def normalize_whitespace(self, text: Optional[str]) -> str:
        """
        Collapse all whitespace to single spaces and trim.

        Args:
            text (Optional[str]): String to normalize, may be None.

        Returns:
            str: Normalized string with single spaces, or empty string if input is None.
        """
        if text is None:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    def sanitize_xml_text(self, text: Optional[str]) -> str:
        """
        Remove illegal control characters and escape standalone ampersands for XML.

        Args:
            text (Optional[str]): Raw text to sanitize.

        Returns:
            str: Text safe for XML, or empty string if input is None or empty.
        """
        if not text:
            return ""
        # Remove control chars except tab, newline, carriage return
        cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)
        # Escape invalid ampersands
        cleaned = re.sub(
            r'&(?!amp;|lt;|gt;|apos;|quot;|#[0-9]+;|#x[0-9A-Fa-f]+;)',
            '&amp;',
            cleaned
        )
        return cleaned.strip()

    def smart_title_case(self, text: Optional[str]) -> str:
        """
        Title-cases a string, keeping small words lowercase (unless first)
        and uppercasing Roman numerals.

        Also prevents capitalizing certain honorifics (e.g., 'chan', 'san') when
        they occur after a hyphen, so 'Onii-chan' stays 'Onii-chan'.

        Args:
            text (Optional[str]): Text to convert.

        Returns:
            str: Smart title-cased text, or empty string if input is None or empty.
        """
        if not text:
            return ""
        # Words to keep lowercase unless first or after a hyphen
        exclusions = {"a", "an", "and", "as", "at", "but", "by", "for",
                      "in", "nor", "of", "on", "or", "the", "to", "with"}
        # Common honorifics to keep lowercase after a hyphen
        honorifics = {"chan", "kun", "san", "sama", "sensei", "senpai", "tan", "dono"}
        # Roman numeral set
        roman_numerals = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
                          "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx"}

        def capitalize_word_part(part: str) -> str:
            # Strip surrounding punctuation
            core = part.strip("\"“”‘’'()[]{}.:;!?,")
            # Uppercase roman numerals
            if core.lower() in roman_numerals:
                return part.replace(core, core.upper())
            # Capitalize first alphabetic character
            for idx, ch in enumerate(part):
                if ch.isalpha():
                    return part[:idx] + ch.upper() + part[idx + 1:]
            return part

        words = text.split()
        result = []
        force_next = False
        for i, word in enumerate(words):
            stripped = word.strip("()[]{}.,:;!?'\"“”‘’")
            lower = stripped.lower()
            # Decide if the word should be capitalized
            if i == 0 or force_next or lower not in exclusions:
                # Preserve hyphens
                parts = re.split(r"(\s*-\s*)", word)
                cased_parts = []
                for idx, part in enumerate(parts):
                    if idx % 2 == 0:  # actual word part
                        part_core = part.strip("\"“”‘’'()[]{}.:;!?,")
                        # If this is after a hyphen and matches an honorific, keep it lowercase
                        if idx > 0 and part_core.lower() in honorifics:
                            cased_parts.append(part.lower())
                        else:
                            cased_parts.append(capitalize_word_part(part))
                    else:
                        cased_parts.append(part)  # keep the hyphen spacing
                cased = "".join(cased_parts)
            else:
                cased = word.lower()
            result.append(cased)
            force_next = (word == "-")
        return " ".join(result)

    def normalize_writer_field(self, writers_raw: Optional[str]) -> str:
        """
        Parses a comma-separated writer list, de-duplicates entries,
        and limits count based on MAX_FILENAME_WRITERS config.

        Args:
            writers_raw (Optional[str]): Comma-separated writer names.

        Returns:
            str: Joined writer names with ', ' or 'Various Artists' if exceeding limit.
        """
        if not writers_raw:
            return ""
        authors = [a.strip() for a in writers_raw.split(",") if a.strip()]
        unique_authors = list(dict.fromkeys(authors))
        max_writers = config_manager.max_filename_writers
        if max_writers == 0 or len(unique_authors) <= max_writers:
            return ", ".join(unique_authors)
        return "Various Artists"

    def normalize_genre_field(self, genres_raw: Optional[str]) -> str:
        """
        Parses a comma-separated genre list, de-duplicates entries,
        and limits count based on MAX_FILENAME_GENRES config.

        Args:
            genres_raw (Optional[str]): Comma-separated genre names.

        Returns:
            str: Joined genre names with ', ' or 'Various Genres' if exceeding limit.
        """
        if not genres_raw:
            return ""
        genres = [g.strip() for g in genres_raw.split(",") if g.strip()]
        unique_genres = list(dict.fromkeys(genres))
        max_genres = config_manager.max_filename_genres
        if max_genres == 0 or len(unique_genres) <= max_genres:
            return ", ".join(unique_genres)
        return "Various Genres"

    def sanitize_path_component(self, name: Optional[str]) -> str:
        """
        Sanitizes a filename or folder name by removing or replacing characters
        forbidden in filesystem paths.

        Args:
            name (Optional[str]): Original component name.

        Returns:
            str: Sanitized component for use in file or folder names.
        """
        if not name:
            return ""
        # Remove forbidden characters (Windows, macOS, Linux)
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', name)
        # Strip trailing dots, spaces, underscores
        return cleaned.strip(" ._")

    def apply_genre_replacements(self, name: str) -> str:
        """
        Applies all substring-based genre replacements to the given genre name.
        Matches are case-insensitive, and only the matching part is replaced.
        """
        result = name
        for wrong, correct in GENRE_REPLACEMENTS:
            # Use case-insensitive replacement of substrings
            pattern = re.compile(re.escape(wrong), re.IGNORECASE)
            result = pattern.sub(correct, result)
        return result
