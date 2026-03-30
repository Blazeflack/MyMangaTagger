# cover_manager.py

"""
Module for managing cover extraction, thumbnail generation, and caching for CBZ files.

This module defines the `CoverManager` class, which provides functionality to extract
cover images from CBZ archives (or use custom overrides), generate thumbnails at a
configured size, and maintain an LRU cache of thumbnails to optimize repeated access.
"""
import zipfile
from pathlib import Path
from collections import OrderedDict
from typing import Dict, Optional, Tuple
from PIL import Image

from services.logger import log
from services.constants import COVER_CACHE_SIZE, THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT


class CoverManager:
    """
    Manages cover extraction, thumbnail creation, and LRU caching for CBZ archives.

    Attributes:
        cache_size (Optional[int]): Maximum number of thumbnails to keep in the LRU cache;
            None means unlimited.
        thumbnail_size (Tuple[int, int]): (width, height) in pixels for generated thumbnails.
        custom_covers (Dict[Path, Path]): Mapping of CBZ file paths to custom cover image paths.
        _cache (OrderedDict[str, Image.Image]): Internal LRU cache mapping resolved CBZ file path
            strings to their generated thumbnail images.
    """

    def __init__(self) -> None:
        """
        Initialize a new CoverManager.

        Uses global constants COVER_CACHE_SIZE, THUMBNAIL_WIDTH, and THUMBNAIL_HEIGHT
        from the application configuration.
        """
        self.cache_size: Optional[int] = COVER_CACHE_SIZE
        self.thumbnail_size: Tuple[int, int] = (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
        # Custom overrides: CBZ -> image path
        self.custom_covers: Dict[Path, Path] = {}
        # LRU cache: resolved CBZ path string -> thumbnail image
        self._cache: OrderedDict[str, Image.Image] = OrderedDict()

    def get_thumbnail(self, cbz_path: Path) -> Image.Image:
        """
        Retrieve or generate a thumbnail for the given CBZ archive.

        If a custom cover override is set for `cbz_path`, that image is used.
        Otherwise, extracts the first valid image from the CBZ, converts WEBP
        to RGBA if needed, and generates a thumbnail of configured size.
        Thumbnails are cached in an LRU cache of size `cache_size`.

        Args:
            cbz_path (Path): Filesystem path to the CBZ archive.

        Returns:
            Image.Image: A PIL Image object representing the thumbnail.

        Raises:
            FileNotFoundError: If no image files are found in the CBZ archive.
        """
        resolved = cbz_path.resolve()

        # Use custom cover if provided
        if resolved in self.custom_covers:
            img = Image.open(self.custom_covers[resolved])
        else:
            key = str(resolved)
            # Return from cache if available
            if key in self._cache:
                img = self._cache.pop(key)
                # Mark as recently used
                self._cache[key] = img
                return img

            # Open archive and locate first valid image
            with zipfile.ZipFile(cbz_path, 'r') as archive:
                # Filter for supported image types and skip metadata entries
                image_names = sorted(
                    [name for name in archive.namelist()
                     if name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))
                     and not name.startswith("__MACOSX/")],
                    key=lambda n: (len(n.split('/')), n.lower())
                )
                if not image_names:
                    log("ERROR", f"No image files found in {cbz_path}")
                    raise FileNotFoundError(f"No image files found in {cbz_path}")

                # Load the first image
                with archive.open(image_names[0]) as fp:
                    img = Image.open(fp)
                    img.load()
                    # Convert WebP formats to RGBA for consistent previews
                    if img.format == 'WEBP':  # type: ignore[attr-defined]
                        img = img.convert('RGBA')

        # Generate thumbnail (in-place)
        img.thumbnail(self.thumbnail_size)

        # Cache only archive-sourced covers
        if resolved not in self.custom_covers:
            key = str(resolved)
            self._cache[key] = img
            # Enforce cache size limit (LRU eviction)
            if self.cache_size and len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)

        return img

    def set_custom_cover(self, cbz_path: Path, image_path: Path) -> None:
        """
        Assign a custom cover image for a specific CBZ archive.

        Overrides any thumbnail extracted from the archive itself. Clears any
        existing cache entry for `cbz_path` so that subsequent calls to
        `get_thumbnail` will use the new custom cover.

        Args:
            cbz_path (Path): Filesystem path to the CBZ archive.
            image_path (Path): Filesystem path to the custom cover image.
        """
        resolved = cbz_path.resolve()
        self.custom_covers[resolved] = image_path
        # Remove any cached thumbnail for this archive
        self._cache.pop(str(resolved), None)

    def clear_custom_cover(self, cbz_path: Path) -> None:
        """
        Remove a custom cover override for a CBZ archive and clear its cache entry.

        After clearing, `get_thumbnail` will extract from the archive again.

        Args:
            cbz_path (Path): Filesystem path to the CBZ archive.
        """
        resolved = cbz_path.resolve()
        self.custom_covers.pop(resolved, None)
        self._cache.pop(str(resolved), None)

    @staticmethod
    def render_for_canvas(
            image: Image.Image,
            canvas_width: int,
            canvas_height: int,
            bg_color: str = "#dddddd"
    ) -> Image.Image:
        """
        Return a PIL.Image.Image resized/padded to fit the canvas, preserving aspect ratio and centering.

        Args:
            image: The source PIL Image.
            canvas_width: Width of target canvas.
            canvas_height: Height of target canvas.
            bg_color: Background color for padding.

        Returns:
            A new PIL.Image.Image sized for the canvas.
        """
        # Prevent zero or negative size
        canvas_width = max(1, canvas_width)
        canvas_height = max(1, canvas_height)
        img_ratio = image.width / image.height
        canvas_ratio = canvas_width / canvas_height

        if img_ratio > canvas_ratio:
            scale = canvas_width / image.width
        else:
            scale = canvas_height / image.height

        new_w = max(1, int(image.width * scale))
        new_h = max(1, int(image.height * scale))
        resized = image.resize((new_w, new_h), Image.LANCZOS)

        background = Image.new("RGB", (canvas_width, canvas_height), bg_color)
        offset_x = (canvas_width - new_w) // 2
        offset_y = (canvas_height - new_h) // 2
        background.paste(resized, (offset_x, offset_y))
        return background
