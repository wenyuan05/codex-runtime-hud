#!/usr/bin/env python3
"""Generate the multi-resolution Windows icon used by Codex Runtime HUD."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from icon_assets import create_icon_image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sizes = (16, 32, 48, 64, 128, 256)
    frames = [create_icon_image(size) for size in sizes]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Pillow uses the first frame as the ICO base and preserves the other
    # frames, allowing Explorer and the taskbar to select an appropriate size.
    frames[-1].save(
        args.output,
        format="ICO",
        append_images=list(reversed(frames[:-1])),
    )
    print(f"Generated {args.output} ({', '.join(f'{s}px' for s in sizes)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
