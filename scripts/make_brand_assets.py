"""Generate the integration's brand images from ControlByWeb's own icon.

    python scripts/make_brand_assets.py

## Why these files live in the repository

A custom integration's icon comes from ``custom_components/<domain>/brand/``. Home Assistant
fetches it through ``/api/brands/integration/{domain}/{image}`` and a local ``brand/`` directory
takes priority over the brands CDN. Nothing is submitted anywhere: ``home-assistant/brands``
explicitly refuses pull requests for custom components, so a 404 from ``brands.home-assistant.io``
is normal and means nothing. HACS also checks for ``brand/icon.png`` directly and fails validation
without it.

## Why only two files, and no dark variants

Home Assistant will ask for ``icon``, ``logo``, their ``@2x`` variants, and a ``dark_`` prefixed
version of each. All of those fall back: ``dark_icon.png`` falls back to ``icon.png``, and
``logo.png`` falls back to the icon. Shipping files that are byte-identical to the ones they fall
back to adds nothing but weight.

Both fallbacks are safe *here specifically*, and it is worth saying why rather than assuming it:

* **No dark variant is needed** because the mark sits on its own opaque teal-to-blue tile. It does
  not depend on what is behind it. The failure this avoids is real -- an icon drawn as ink on a
  transparent background renders as an invisible or muddy blob on one of the two themes, and is
  only ever noticed on whichever theme the author does not use. Verified by compositing the icon
  onto both a white and a near-black backdrop and looking at the result.
* **No logo is needed** because ControlByWeb's wordmark is not available as an asset here, and
  drawing an approximation of a company's wordmark would be worse than the fallback: it would be
  wrong, and it would look deliberate.

## Why this downloads rather than vendoring artwork

The source is ControlByWeb's own published icon, so the script records exactly where it came from
and re-fetches it. A copy pasted into the repository with no provenance is the thing that later
nobody can verify or update.
"""

from __future__ import annotations

import io
import sys
import urllib.request
from pathlib import Path

from PIL import Image

SOURCE_URL = "https://controlbyweb.com/wp-content/uploads/2024/06/cropped-CBW-Favicon-V2.png"
"""ControlByWeb's site icon, published at 512x512 with an alpha channel."""

BRAND_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "controlbyweb" / "brand"

#: Home Assistant's brands specification: `icon.png` is 256x256 and `icon@2x.png` is 512x512.
#: Both are square, and both are exact -- a 255px icon is rejected, not scaled.
OUTPUTS = {"icon.png": 256, "icon@2x.png": 512}


def main() -> int:
    """Fetch the source icon and write the brand images."""
    # A User-Agent is required, not cosmetic: controlbyweb.com answers urllib's
    # default `Python-urllib/3.x` with 403 Forbidden and serves the same URL
    # normally to a browser string.
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        source = Image.open(io.BytesIO(response.read())).convert("RGBA")

    if source.size[0] != source.size[1]:
        # A non-square source would be letterboxed into a square icon, which reads
        # as a mistake rather than as a logo. Better to stop and look at it.
        print(f"source is {source.size}, expected a square image", file=sys.stderr)
        return 1

    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    for name, size in OUTPUTS.items():
        target = BRAND_DIR / name
        source.resize((size, size), Image.LANCZOS).save(target, "PNG", optimize=True)
        print(f"wrote {target.relative_to(BRAND_DIR.parents[2])} ({size}x{size})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
