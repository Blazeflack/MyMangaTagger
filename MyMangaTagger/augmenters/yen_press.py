# augmenters/yen_press.py

"""Yen Press volume metadata augmenter."""

import re

from augmenters.base import (
    BaseVolumeAugmenter,
    VolumeAugmentationError,
    VolumeMetadataPatch,
    extract_all_links,
    extract_block_by_class,
    extract_block_by_id,
    extract_first_tag_text,
    extract_title_tag,
    get_meta_content,
    normalize_number,
    parse_date_text,
)


class YenPressAugmenter(BaseVolumeAugmenter):
    """Scrape volume-specific metadata from Yen Press volume pages."""

    source_key = "yen_press"
    source_name = "Yen Press"
    url_patterns = ["yenpress.com/series/", "yenpress.com/titles/"]

    def fetch_patches(self, url: str) -> dict[str, VolumeMetadataPatch]:
        """Fetch volume patches from a Yen Press series or volume URL.

        Args:
            url: Yen Press series URL, or a single volume URL.

        Returns:
            Mapping of normalized volume number to patch.

        Raises:
            VolumeAugmentationError: If no usable patches can be built.
        """
        volume_urls = self._get_volume_urls(url)
        if not volume_urls:
            raise VolumeAugmentationError("[Yen Press] No volume links found.")

        patches: dict[str, VolumeMetadataPatch] = {}
        for volume_url in volume_urls:
            patch = self._fetch_volume_patch(volume_url)
            if patch and patch.number:
                patches[patch.number] = patch

        if not patches:
            raise VolumeAugmentationError("[Yen Press] No usable volume metadata found.")
        return patches

    def _get_volume_urls(self, url: str) -> list[str]:
        """Return volume URLs from a series page or a single volume URL.

        Args:
            url: Yen Press URL.

        Returns:
            Deduplicated volume URLs.
        """
        if "/titles/" in url.lower():
            return [url]

        page_html = self._fetch_text(url)
        volumes_block = extract_block_by_id(page_html, "volumes-list")
        links = extract_all_links(volumes_block or page_html, url)
        return [link for link in links if "/titles/" in link.lower()]

    def _fetch_volume_patch(self, url: str) -> VolumeMetadataPatch | None:
        """Fetch and parse one Yen Press volume page.

        Yen Press stores the volume-specific subtitle and summary together in
        ``div.content-heading-txt``. When present, the ``h2`` is used as the
        title suffix and the first ``p`` is used as the summary.

        Args:
            url: Volume page URL.

        Returns:
            Volume metadata patch, or None if no number can be found.
        """
        page_html = self._fetch_text(url)
        page_title = extract_title_tag(page_html)
        number = self._extract_number(url, page_title)
        if not number:
            return None

        content_block = extract_block_by_class(page_html, "content-heading-txt", "div")
        title = extract_first_tag_text(content_block, "h2")
        summary = extract_first_tag_text(content_block, "p") or get_meta_content(page_html, "description")

        book_details = extract_block_by_class(page_html, "book-details", "section") or page_html
        active_details = extract_block_by_class(book_details, "active", "div") or book_details
        year, month, day = parse_date_text(active_details)

        return VolumeMetadataPatch(
            number=number,
            title=title,
            summary=summary,
            year=year,
            month=month,
            day=day,
            source_url=url,
        )

    @staticmethod
    def _extract_number(url: str, title: str) -> str:
        """Extract a volume number from a Yen Press URL or title.

        Args:
            url: Volume page URL.
            title: Page title text.

        Returns:
            Normalized number, or an empty string.
        """
        for value in (url, title):
            match = re.search(r"\bvol(?:ume)?[-.\s]*(\d+)\b", value, flags=re.IGNORECASE)
            if match:
                return normalize_number(match.group(1))
        return ""