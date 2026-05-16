# augmenters/base.py

"""Shared helpers for publisher-specific volume metadata augmentation.

Augmenters fetch volume-specific metadata from publisher pages and return
small patches that can be applied on top of existing source metadata. They do
not return full ComicInfo records.
"""

import html
import importlib
import json
import re
import requests

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urljoin, urlparse
from services.normalization import Normalizer


class VolumeAugmentationError(Exception):
    """Raised when volume metadata augmentation fails."""


@dataclass
class VolumeMetadataPatch:
    """Metadata patch for one numbered volume.

    Attributes:
        number: ComicInfo volume number used to match selected files.
        title: Optional volume-specific title suffix to append to the current title.
        summary: Optional replacement summary for the volume.
        year: Optional release year.
        month: Optional release month.
        day: Optional release day.
        source_url: Publisher volume URL used to build this patch, if known.
    """

    number: str
    title: str = ""
    summary: str = ""
    year: str = ""
    month: str = ""
    day: str = ""
    source_url: str = ""


@dataclass
class VolumeAugmentationPreviewRow:
    """Before/after preview data for one selected file.

    Attributes:
        path: Selected CBZ path for this preview row.
        number: Normalized ComicInfo number used for patch matching.
        title_before: Title before applying the patch.
        title_after: Title after applying the patch.
        summary_status: Human-friendly summary change status.
        date_before: Existing release date shown as YYYY-MM-DD where available.
        date_after: Patched release date shown as YYYY-MM-DD where available.
        status: Human-friendly match/change status.
    """

    path: Path
    number: str
    title_before: str
    title_after: str
    summary_status: str
    date_before: str
    date_after: str
    status: str


class BaseVolumeAugmenter(ABC):
    """Abstract base class for publisher-specific volume metadata augmenters.

    Subclasses self-register through ``source_key`` and are detected from URL
    patterns. Each subclass returns patches keyed by normalized ComicInfo volume
    number.
    """

    _registry: ClassVar[dict[str, type["BaseVolumeAugmenter"]]] = {}
    source_key: ClassVar[str] = ""
    source_name: ClassVar[str] = ""
    url_patterns: ClassVar[list[str]] = []

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Register concrete augmenter subclasses automatically."""
        super().__init_subclass__(**kwargs)
        key = getattr(cls, "source_key", "")
        if key:
            BaseVolumeAugmenter._registry[key] = cls

    @classmethod
    def detect_from_url(cls, url: str) -> str | None:
        """Return the augmenter key that supports a URL.

        Args:
            url: Publisher URL supplied by the user.

        Returns:
            Matching augmenter key, or None if no augmenter supports the URL.
        """
        url_lower = url.lower()
        for key, augmenter_cls in cls._registry.items():
            for pattern in augmenter_cls.url_patterns:
                if pattern in url_lower:
                    return key
        return None

    @classmethod
    def get_augmenter_for_url(cls, url: str) -> "BaseVolumeAugmenter | None":
        """Create an augmenter instance for a supported URL.

        Args:
            url: Publisher URL supplied by the user.

        Returns:
            Augmenter instance, or None when the URL is unsupported.
        """
        key = cls.detect_from_url(url)
        if not key:
            return None
        return cls._registry[key]()

    @abstractmethod
    def fetch_patches(self, url: str) -> dict[str, VolumeMetadataPatch]:
        """Fetch volume patches from a publisher URL.

        Args:
            url: Publisher series URL supplied by the user.

        Returns:
            Mapping of normalized volume number to volume metadata patch.

        Raises:
            VolumeAugmentationError: If fetching or parsing fails.
        """
        raise NotImplementedError

    def _fetch_text(self, url: str) -> str:
        """Fetch text from a URL with normal browser-like request headers.

        Some publisher sites reject minimal script-style requests even when the
        same URL opens normally in a browser. The fuller header set keeps the
        request closer to a normal page visit and makes fetch failures easier to
        diagnose by including the HTTP status code when available.

        Args:
            url: URL to fetch.

        Returns:
            Response body text.

        Raises:
            VolumeAugmentationError: If the HTTP request fails.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=25,
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding or response.encoding
            return response.text
        except requests.RequestException as exc:
            status_code = ""
            if exc.response is not None:
                status_code = f" HTTP status: {exc.response.status_code}."

            raise VolumeAugmentationError(
                f"[{self.source_name}] Could not fetch URL: {url}.{status_code}"
            ) from exc

    def _fetch_json(self, url: str) -> Any:
        """Fetch JSON from a URL.

        Args:
            url: URL to fetch.

        Returns:
            Parsed JSON payload.

        Raises:
            VolumeAugmentationError: If fetching or JSON parsing fails.
        """
        text = self._fetch_text(url)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise VolumeAugmentationError(
                f"[{self.source_name}] Response was not valid JSON: {url}"
            ) from exc


# Importing the concrete modules registers their classes via __init_subclass__.
_AUGMENTER_MODULES = [
    "augmenters.jnovel_club",
    "augmenters.yen_press",
    "augmenters.seven_seas",
    "augmenters.kodansha",
    "augmenters.one_peace_books",
]


def load_all_augmenters() -> None:
    """Import all built-in augmenter modules so they self-register."""
    for module_name in _AUGMENTER_MODULES:
        importlib.import_module(module_name)


def get_augmenter_for_url(url: str) -> BaseVolumeAugmenter | None:
    """Return an augmenter instance that supports the supplied URL.

    Args:
        url: Publisher URL supplied by the user.

    Returns:
        Augmenter instance, or None when no registered augmenter supports it.
    """
    load_all_augmenters()
    return BaseVolumeAugmenter.get_augmenter_for_url(url)


def normalize_whitespace(value: Any) -> str:
    """Collapse whitespace and HTML-unescape text.

    Args:
        value: Value to normalize.

    Returns:
        Cleaned string, or an empty string when the value is missing.
    """
    if value is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(str(value))).strip()


def normalize_patch_title(title: str) -> str:
    """Normalize publisher-provided volume title suffixes.

    Publisher pages sometimes use all-caps or all-lowercase marketing headings
    as volume subtitles. This helper keeps already mixed-case titles unchanged,
    but converts mostly-uppercase or mostly-lowercase titles into the app's
    normal smart title case.

    Args:
        title: Publisher-provided title suffix.

    Returns:
        Cleaned title suffix, with mostly single-case text normalized.
    """
    cleaned = normalize_whitespace(title)
    if not cleaned:
        return ""

    letters = [character for character in cleaned if character.isalpha()]
    if not letters:
        return cleaned

    uppercase_count = sum(1 for character in letters if character.isupper())
    lowercase_count = sum(1 for character in letters if character.islower())

    uppercase_ratio = uppercase_count / len(letters)
    lowercase_ratio = lowercase_count / len(letters)

    # Be conservative: only normalize text that clearly looks like an all-caps
    # or all-lowercase heading. This avoids altering intentional mixed-case
    # publisher titles.
    if uppercase_ratio < 0.8 and lowercase_ratio < 0.8:
        return cleaned

    normalizer = Normalizer()
    return normalizer.smart_title_case(cleaned.lower())


def strip_html(value: str) -> str:
    """Remove HTML tags and normalize the resulting text.

    Args:
        value: HTML fragment.

    Returns:
        Plain text with collapsed whitespace.
    """
    text = re.sub(r"<\s*br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return normalize_whitespace(text)


def normalize_number(value: Any) -> str:
    """Normalize a ComicInfo or publisher volume number for matching.

    Args:
        value: Raw number value.

    Returns:
        Integer-like volume number string, or an empty string if unusable.
    """
    if value is None:
        return ""

    text = normalize_whitespace(value)
    if not text:
        return ""

    # Accept values like "1", "1.0", or "Vol. 1".
    exact = re.fullmatch(r"(\d+)(?:\.0+)?", text)
    if exact:
        return exact.group(1)

    embedded = re.search(r"\b(?:vol(?:ume)?\.?\s*)?(\d+)\b", text, flags=re.IGNORECASE)
    return embedded.group(1) if embedded else ""


def date_tuple_from_timestamp(seconds: Any) -> tuple[str, str, str]:
    """Convert a Unix timestamp to ComicInfo date fields.

    Args:
        seconds: Unix timestamp value.

    Returns:
        Three-tuple of strings: year, month, day.
    """
    try:
        timestamp = int(str(seconds).strip())
    except (TypeError, ValueError):
        return "", "", ""

    dt = datetime.fromtimestamp(timestamp, UTC)
    return dt.strftime("%Y"), dt.strftime("%m"), dt.strftime("%d")


def parse_date_text(text: str) -> tuple[str, str, str]:
    """Extract a date from publisher text.

    Supports common publisher date formats, including ISO-style dates,
    English month-name dates, and numeric US-style dates used by Kodansha.

    Supported examples:
        - 2024-03-26
        - 2024/03/26
        - March 26, 2024
        - Mar. 26, 2024
        - 6/13/2023

    Args:
        text: Text containing a release date.

    Returns:
        Three-tuple of strings: year, month, day. Empty strings indicate no date.
    """
    cleaned = normalize_whitespace(text)
    if not cleaned:
        return "", "", ""

    # ISO-like dates, commonly found in structured data:
    # 2023-06-13, 2024-03-27T17:00:00Z, 2023/06/13, 2023.06.13
    iso_match = re.search(
        r"\b(20\d{2}|19\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?=$|[^\d])",
        cleaned,
    )
    if iso_match:
        year, month, day = iso_match.groups()
        return year, f"{int(month):02d}", f"{int(day):02d}"

    # US-style numeric dates, used by Kodansha volume pages:
    # 6/13/2023
    numeric_us_match = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2}|19\d{2})\b", cleaned)
    if numeric_us_match:
        month, day, year = numeric_us_match.groups()
        return year, f"{int(month):02d}", f"{int(day):02d}"

    # English month-name dates, used by several publisher pages:
    # March 26, 2024, Mar. 26, 2024
    month_names = (
        "January|February|March|April|May|June|July|August|September|"
        "October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    )
    text_match = re.search(
        rf"\b({month_names})\.?\s+(\d{{1,2}}),?\s+(20\d{{2}}|19\d{{2}})\b",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not text_match:
        return "", "", ""

    month_text, day, year = text_match.groups()
    month_lookup = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }
    month = month_lookup.get(month_text.lower().rstrip("."), 0)
    if not month:
        return "", "", ""
    return year, f"{month:02d}", f"{int(day):02d}"


def format_date(meta: dict[str, str]) -> str:
    """Format year/month/day fields for preview display.

    Args:
        meta: Metadata dictionary with lowercase ComicInfo date keys.

    Returns:
        Date string with missing parts omitted.
    """
    parts = [meta.get("year", ""), meta.get("month", ""), meta.get("day", "")]
    return "-".join(part for part in parts if part)


def make_absolute_url(base_url: str, href: str) -> str:
    """Build an absolute URL from a page URL and a link href.

    Args:
        base_url: Page URL containing the link.
        href: Raw href value.

    Returns:
        Absolute URL without surrounding whitespace.
    """
    return urljoin(base_url, html.unescape(href).strip())


def get_meta_content(page_html: str, key: str) -> str:
    """Extract a meta tag content value by name or property.

    Args:
        page_html: Full page HTML.
        key: Meta name/property to find.

    Returns:
        Meta content text, or an empty string when missing.
    """
    pattern = (
        rf"<meta\b(?=[^>]*(?:name|property)=[\"']{re.escape(key)}[\"'])"
        rf"[^>]*content=[\"']([^\"']*)[\"'][^>]*>"
    )
    match = re.search(pattern, page_html, flags=re.IGNORECASE | re.DOTALL)
    return normalize_whitespace(match.group(1)) if match else ""


def extract_title_tag(page_html: str) -> str:
    """Extract a page's title tag text.

    Args:
        page_html: Full page HTML.

    Returns:
        Title tag text, or an empty string when missing.
    """
    match = re.search(r"<title[^>]*>(.*?)</title>", page_html, flags=re.IGNORECASE | re.DOTALL)
    return strip_html(match.group(1)) if match else ""


def extract_block_by_id(page_html: str, element_id: str) -> str:
    """Extract the first HTML block whose start tag has a specific id.

    Args:
        page_html: Full page HTML.
        element_id: id attribute to search for.

    Returns:
        Best-effort HTML fragment for the block, or an empty string.
    """
    pattern = rf"<(?P<tag>\w+)\b(?=[^>]*\bid=[\"']{re.escape(element_id)}[\"'])[^>]*>"
    match = re.search(pattern, page_html, flags=re.IGNORECASE)
    if not match:
        return ""
    return _extract_block_from_match(page_html, match)


def extract_block_by_class(page_html: str, class_name: str, tag_name: str | None = None) -> str:
    """Extract the first HTML block whose start tag contains a CSS class.

    Args:
        page_html: Full page HTML.
        class_name: CSS class to search for.
        tag_name: Optional tag name restriction, such as ``div`` or ``section``.

    Returns:
        Best-effort HTML fragment for the block, or an empty string.
    """
    tag = tag_name or r"\w+"
    pattern = (
        rf"<(?P<tag>{tag})\b(?=[^>]*\bclass=[\"'][^\"']*"
        rf"\b{re.escape(class_name)}\b[^\"']*[\"'])[^>]*>"
    )
    match = re.search(pattern, page_html, flags=re.IGNORECASE)
    if not match:
        return ""
    return _extract_block_from_match(page_html, match)


def extract_all_links(fragment: str, base_url: str) -> list[str]:
    """Extract all href values from an HTML fragment.

    Args:
        fragment: HTML fragment to inspect.
        base_url: URL used to resolve relative href values.

    Returns:
        Deduplicated absolute URLs in source order.
    """
    links: list[str] = []
    seen: set[str] = set()
    for href in re.findall(r"<a\b[^>]*\bhref=[\"']([^\"']+)[\"']", fragment, flags=re.IGNORECASE):
        absolute = make_absolute_url(base_url, href).split("#", 1)[0]
        if absolute and absolute not in seen:
            links.append(absolute)
            seen.add(absolute)
    return links


def extract_first_tag_text(fragment: str, tag_name: str) -> str:
    """Extract text from the first matching tag in an HTML fragment.

    Args:
        fragment: HTML fragment to inspect.
        tag_name: Tag name to extract.

    Returns:
        Plain text inside the first matching tag, or an empty string.
    """
    match = re.search(
        rf"<{re.escape(tag_name)}\b[^>]*>(.*?)</{re.escape(tag_name)}>",
        fragment,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return strip_html(match.group(1)) if match else ""


def extract_json_ld_objects(page_html: str) -> list[Any]:
    """Extract JSON-LD payloads from a page.

    Args:
        page_html: Full page HTML.

    Returns:
        Parsed JSON-LD objects. Invalid script blocks are skipped.
    """
    payloads: list[Any] = []
    pattern = r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>"
    for script_text in re.findall(pattern, page_html, flags=re.IGNORECASE | re.DOTALL):
        try:
            payloads.append(json.loads(html.unescape(script_text.strip())))
        except json.JSONDecodeError:
            continue
    return payloads


def extract_extra_volume_title(full_title: str, number: str) -> str:
    """Extract only the volume-specific subtitle from a publisher title.

    Examples:
        ``Series, Vol. 10: Subtitle`` -> ``Subtitle``
        ``Series Volume 10 - Subtitle`` -> ``Subtitle``

    Args:
        full_title: Publisher volume title.
        number: Normalized volume number.

    Returns:
        Subtitle-only string, or an empty string if no subtitle is found.
    """
    title = normalize_whitespace(full_title)
    if not title or not number:
        return ""

    # Remove common publisher suffixes from title tags/meta titles.
    title = re.sub(r"\s*[|\-]\s*(Yen Press|Seven Seas Entertainment|Kodansha)\s*$", "", title, flags=re.IGNORECASE)

    patterns = [
        rf"\bVol\.?\s*{re.escape(number)}\s*[:\-–—]\s*(.+)$",
        rf"\bVolume\s*{re.escape(number)}\s*[:\-–—]\s*(.+)$",
        rf"\b{re.escape(number)}\s*\([^)]*\)\s*[:\-–—]\s*(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, title, flags=re.IGNORECASE)
        if match:
            return normalize_whitespace(match.group(1))
    return ""


def build_preview_rows(
    paths: list[Path],
    metadata_by_path: dict[Path, dict[str, str]],
    patches: dict[str, VolumeMetadataPatch],
) -> list[VolumeAugmentationPreviewRow]:
    """Build preview rows for selected files and fetched patches.

    Args:
        paths: Selected file paths in UI order.
        metadata_by_path: Current in-memory metadata by file path.
        patches: Volume patches keyed by normalized volume number.

    Returns:
        Preview rows showing before/after values and status.
    """
    rows: list[VolumeAugmentationPreviewRow] = []
    for path in paths:
        meta = metadata_by_path.get(path, {})
        number = normalize_number(meta.get("number", ""))
        before_date = format_date(meta)
        title_before = meta.get("title", "")

        if not number:
            rows.append(
                VolumeAugmentationPreviewRow(
                    path=path,
                    number="",
                    title_before=title_before,
                    title_after=title_before,
                    summary_status="Missing",
                    date_before=before_date,
                    date_after=before_date,
                    status="Missing number",
                )
            )
            continue

        patch = patches.get(number)
        if patch is None:
            rows.append(
                VolumeAugmentationPreviewRow(
                    path=path,
                    number=number,
                    title_before=title_before,
                    title_after=title_before,
                    summary_status="Missing",
                    date_before=before_date,
                    date_after=before_date,
                    status="No matching volume",
                )
            )
            continue

        preview_meta = apply_patch_to_metadata(meta, patch)
        rows.append(
            VolumeAugmentationPreviewRow(
                path=path,
                number=number,
                title_before=title_before,
                title_after=preview_meta.get("title", ""),
                summary_status=_summary_status(meta, preview_meta, patch),
                date_before=before_date,
                date_after=format_date(preview_meta),
                status=_patch_status(meta, preview_meta, patch),
            )
        )
    return rows


def apply_patches_to_metadata(
    paths: list[Path],
    metadata_by_path: dict[Path, dict[str, str]],
    patches: dict[str, VolumeMetadataPatch],
) -> int:
    """Apply matching patches to in-memory metadata.

    Args:
        paths: Selected file paths in UI order.
        metadata_by_path: Current in-memory metadata by file path.
        patches: Volume patches keyed by normalized volume number.

    Returns:
        Number of selected files that received a matching patch.
    """
    applied_count = 0
    for path in paths:
        meta = metadata_by_path.setdefault(path, {})
        number = normalize_number(meta.get("number", ""))
        if not number or number not in patches:
            continue

        metadata_by_path[path] = apply_patch_to_metadata(meta, patches[number])
        applied_count += 1
    return applied_count


def apply_patch_to_metadata(
    meta: dict[str, str],
    patch: VolumeMetadataPatch,
) -> dict[str, str]:
    """Return metadata with a volume patch applied.

    Args:
        meta: Existing ComicInfo metadata for one file.
        patch: Volume-specific metadata patch.

    Returns:
        New metadata dictionary with only augmentation fields changed.
    """
    updated = dict(meta)

    title_suffix = normalize_patch_title(patch.title)
    if title_suffix:
        current_title = normalize_whitespace(updated.get("title", ""))
        if current_title and not current_title.lower().endswith(title_suffix.lower()):
            updated["title"] = f"{current_title} - {title_suffix}"
        elif not current_title:
            updated["title"] = title_suffix

    summary = patch.summary.strip()
    if summary:
        updated["summary"] = summary

    for key in ("year", "month", "day"):
        value = getattr(patch, key)
        if value:
            updated[key] = value

    return updated


def _summary_status(
    old_meta: dict[str, str],
    new_meta: dict[str, str],
    patch: VolumeMetadataPatch,
) -> str:
    """Return a compact summary preview status."""
    if not patch.summary:
        return "Missing"
    return "Changed" if old_meta.get("summary", "") != new_meta.get("summary", "") else "Unchanged"


def _patch_status(
    old_meta: dict[str, str],
    new_meta: dict[str, str],
    patch: VolumeMetadataPatch,
) -> str:
    """Return a compact row status for a patch preview."""
    if old_meta == new_meta:
        return "Matched, no changes"
    changed_fields = []
    for key in ("title", "summary", "year", "month", "day"):
        if old_meta.get(key, "") != new_meta.get(key, ""):
            changed_fields.append(key)
    return "Changed: " + ", ".join(changed_fields) if changed_fields else "Matched"


def _extract_block_from_match(page_html: str, match: re.Match[str]) -> str:
    """Best-effort extraction of a balanced HTML block from a start-tag match."""
    tag = match.group("tag")
    start = match.start()
    open_close_pattern = re.compile(rf"</?{re.escape(tag)}\b[^>]*>", flags=re.IGNORECASE)
    depth = 0
    for tag_match in open_close_pattern.finditer(page_html, pos=start):
        text = tag_match.group(0)
        if text.startswith("</"):
            depth -= 1
            if depth == 0:
                return page_html[start:tag_match.end()]
        else:
            depth += 1
    return page_html[start:]