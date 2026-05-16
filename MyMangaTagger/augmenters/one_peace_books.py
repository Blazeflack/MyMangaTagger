# augmenters/one_peace_books.py

# augmenters/one_peace_books.py

"""One Peace Books volume metadata augmenter."""

from __future__ import annotations

import re

from augmenters.base import (
    BaseVolumeAugmenter,
    VolumeAugmentationError,
    VolumeMetadataPatch,
    extract_extra_volume_title,
    normalize_number,
    normalize_whitespace,
    strip_html,
)


class OnePeaceBooksAugmenter(BaseVolumeAugmenter):
    """Scrape volume-specific metadata from One Peace Books series pages.

    One Peace Books generally lists all volumes for a series on a single HTML
    page. Each volume is represented by a ``div.newbook-case-detail`` block,
    followed by a matching ``div.newbook-case-outline`` block containing the
    summary.

    One Peace Books only exposes the publication year, so this augmenter fills
    ``year`` while leaving ``month`` and ``day`` empty.
    """

    source_key = "one_peace_books"
    source_name = "One Peace Books"
    url_patterns = [
        "onepeacebooks.com/jt/",
        "onepeacebooks.com/op/",
    ]

    def fetch_patches(self, url: str) -> dict[str, VolumeMetadataPatch]:
        """Fetch volume patches from a One Peace Books series page.

        Args:
            url: One Peace Books series URL.

        Returns:
            Mapping of normalized volume number to patch.

        Raises:
            VolumeAugmentationError: If no usable volume patches can be built.
        """
        page_html = self._fetch_text(url)
        volume_entries = self._extract_volume_entries(page_html)

        patches: dict[str, VolumeMetadataPatch] = {}
        for detail_block, outline_block in volume_entries:
            patch = self._build_patch(detail_block, outline_block, url)
            if patch and patch.number:
                patches[patch.number] = patch

        if not patches:
            raise VolumeAugmentationError(
                "[One Peace Books] No usable volume metadata found."
            )

        return patches

    def _build_patch(
        self,
        detail_block: str,
        outline_block: str,
        url: str,
    ) -> VolumeMetadataPatch | None:
        """Build one patch from a volume detail block and summary block.

        Args:
            detail_block: HTML fragment containing title and book metadata.
            outline_block: HTML fragment containing the volume summary.
            url: Source page URL.

        Returns:
            Volume metadata patch, or None if the volume number is missing.
        """
        full_title = self._extract_first_class_text(detail_block, "booktitle")
        number = self._extract_number(full_title)
        if not number:
            return None

        summary = self._extract_first_class_text(outline_block, "book-detail-text")
        year = self._extract_published_year(detail_block)

        return VolumeMetadataPatch(
            number=number,
            title=extract_extra_volume_title(full_title, number),
            summary=summary,
            year=year,
            month="",
            day="",
            source_url=url,
        )

    @staticmethod
    def _extract_volume_entries(page_html: str) -> list[tuple[str, str]]:
        """Extract paired volume detail and outline blocks from a page.

        Args:
            page_html: Full One Peace Books page HTML.

        Returns:
            List of ``(detail_block, outline_block)`` pairs in page order.
        """
        entries: list[tuple[str, str]] = []

        # Each volume starts with a detail block and is followed by the summary
        # outline block. The next detail block marks the end of the current
        # entry.
        pattern = (
            r"(<div\b[^>]*class=[\"'][^\"']*\bnewbook-case-detail\b[^\"']*[\"'][^>]*>.*?</div>\s*</div>)"
            r"\s*"
            r"(<div\b[^>]*class=[\"'][^\"']*\bnewbook-case-outline\b[^\"']*[\"'][^>]*>.*?</div>\s*</div>)"
        )

        for match in re.finditer(pattern, page_html, flags=re.IGNORECASE | re.DOTALL):
            detail_block = match.group(1)
            outline_block = match.group(2)
            entries.append((detail_block, outline_block))

        return entries

    @staticmethod
    def _extract_first_class_text(fragment: str, class_name: str) -> str:
        """Extract text from the first tag with a specific CSS class.

        Args:
            fragment: HTML fragment to inspect.
            class_name: CSS class to search for.

        Returns:
            Plain text from the first matching element, or an empty string.
        """
        pattern = (
            rf"<(?P<tag>\w+)\b(?=[^>]*class=[\"'][^\"']*"
            rf"\b{re.escape(class_name)}\b[^\"']*[\"'])[^>]*>"
            rf"(?P<text>.*?)</(?P=tag)>"
        )
        match = re.search(pattern, fragment, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return ""

        return strip_html(match.group("text"))

    @staticmethod
    def _extract_number(title: str) -> str:
        """Extract a volume number from a One Peace Books volume title.

        Args:
            title: Volume title, such as ``The New Gate Volume 16``.

        Returns:
            Normalized volume number, or an empty string.
        """
        cleaned = normalize_whitespace(title)
        match = re.search(r"\bvolume\s+(\d+)\b", cleaned, flags=re.IGNORECASE)
        if not match:
            return ""

        return normalize_number(match.group(1))

    @staticmethod
    def _extract_published_year(detail_block: str) -> str:
        """Extract the published year from a volume detail block.

        Args:
            detail_block: HTML fragment containing book metadata.

        Returns:
            Four-digit publication year, or an empty string.
        """
        detail_text = strip_html(detail_block)
        match = re.search(r"\bPublished:\s*(20\d{2}|19\d{2})\b", detail_text)
        if not match:
            return ""

        return match.group(1)