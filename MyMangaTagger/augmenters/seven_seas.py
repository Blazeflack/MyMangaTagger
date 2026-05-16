# augmenters/seven_seas.py

"""Seven Seas Entertainment volume metadata augmenter."""

import re

from augmenters.base import (
    BaseVolumeAugmenter,
    VolumeAugmentationError,
    VolumeMetadataPatch,
    extract_all_links,
    extract_block_by_class,
    extract_block_by_id,
    extract_extra_volume_title,
    extract_title_tag,
    get_meta_content,
    normalize_number,
    normalize_whitespace,
    parse_date_text,
    strip_html,
)


class SevenSeasAugmenter(BaseVolumeAugmenter):
    """Scrape volume-specific metadata from Seven Seas volume pages."""

    source_key = "seven_seas"
    source_name = "Seven Seas Entertainment"
    url_patterns = [
        "sevenseasentertainment.com/series/",
        "sevenseasentertainment.com/books/",
    ]

    def fetch_patches(self, url: str) -> dict[str, VolumeMetadataPatch]:
        """Fetch volume patches from a Seven Seas series or volume URL.

        Args:
            url: Seven Seas series URL, or a single volume URL.

        Returns:
            Mapping of normalized volume number to patch.

        Raises:
            VolumeAugmentationError: If no usable patches can be built.
        """
        volume_urls = self._get_volume_urls(url)
        if not volume_urls:
            raise VolumeAugmentationError("[Seven Seas] No volume links found.")

        patches: dict[str, VolumeMetadataPatch] = {}
        for volume_url in volume_urls:
            patch = self._fetch_volume_patch(volume_url)
            if patch and patch.number:
                patches[patch.number] = patch

        if not patches:
            raise VolumeAugmentationError("[Seven Seas] No usable volume metadata found.")
        return patches

    def _get_volume_urls(self, url: str) -> list[str]:
        """Return volume URLs from a series page or a single volume URL.

        Args:
            url: Seven Seas URL.

        Returns:
            Deduplicated volume URLs.
        """
        if "/books/" in url.lower():
            return [url]

        page_html = self._fetch_text(url)
        volumes_block = extract_block_by_class(page_html, "volumes-container", "div")
        links = extract_all_links(volumes_block or page_html, url)
        return [link for link in links if "/books/" in link.lower()]

    def _fetch_volume_patch(self, url: str) -> VolumeMetadataPatch | None:
        """Fetch and parse one Seven Seas volume page.

        Seven Seas stores the volume-specific subtitle and summary together in
        ``div.description-content``. The first paragraph is usually a short
        volume title or promotional heading, while the remaining paragraphs are
        the real summary.

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

        description_block = extract_block_by_class(page_html, "description-content", "div")
        volume_title, summary = self._extract_title_and_summary(description_block)

        # Fall back to the browser title only when the description block does
        # not contain a usable volume-specific title.
        if not volume_title:
            volume_title = extract_extra_volume_title(page_title, number)

        # Only use the meta description if the dedicated description block is
        # missing entirely. When the block exists but only contains one paragraph,
        # that paragraph is usually a heading, not a summary.
        if not description_block and not summary:
            summary = get_meta_content(page_html, "description")

        volume_meta = extract_block_by_id(page_html, "volume-meta") or page_html
        year, month, day = parse_date_text(volume_meta)

        return VolumeMetadataPatch(
            number=number,
            title=volume_title,
            summary=summary,
            year=year,
            month=month,
            day=day,
            source_url=url,
        )

    @staticmethod
    def _extract_title_and_summary(description_block: str) -> tuple[str, str]:
        """Extract Seven Seas volume title and summary from description content.

        Seven Seas volume pages commonly use the first paragraph in
        ``div.description-content`` as a short subtitle or promotional heading.
        Remaining paragraphs are treated as the actual summary.

        Args:
            description_block: HTML fragment from ``div.description-content``.

        Returns:
            Two-tuple containing the volume title and summary. Either value may
            be empty if it is not available.
        """
        if not description_block:
            return "", ""

        paragraph_matches = re.findall(
            r"<p\b[^>]*>(.*?)</p>",
            description_block,
            flags=re.IGNORECASE | re.DOTALL,
        )

        paragraphs = [
            strip_html(paragraph)
            for paragraph in paragraph_matches
        ]
        paragraphs = [paragraph for paragraph in paragraphs if paragraph]

        if not paragraphs:
            return "", ""

        volume_title = normalize_whitespace(paragraphs[0])
        summary = "\n\n".join(paragraphs[1:]).strip()

        return volume_title, summary

    @staticmethod
    def _extract_number(url: str, title: str) -> str:
        """Extract a volume number from a Seven Seas URL or title.

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