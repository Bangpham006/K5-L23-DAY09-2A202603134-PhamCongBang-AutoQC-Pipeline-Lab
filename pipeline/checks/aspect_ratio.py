"""Check thưởng — kiểm tra tỉ lệ khung hình bất thường của bounding box (aspect ratio extreme)."""
from PIL import Image

from ..common import WARN, Issue


def run(ds, cfg):
    max_ratio = cfg.get("aspect_ratio", {}).get("max_ratio", 10.0)
    issues = []
    for p in ds.image_files():
        lbl_p = ds.label_path(p.stem)
        if not lbl_p.exists():
            continue
        try:
            with Image.open(p) as im:
                im_w, im_h = im.size
        except Exception:
            continue

        try:
            lines = lbl_p.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue

        for i, line in enumerate(lines, start=1):
            parts = line.strip().split()
            if len(parts) != 5:
                continue
            try:
                _cls, _cx, _cy, w, h = map(float, parts)
            except ValueError:
                continue
            px_w = w * im_w
            px_h = h * im_h
            if px_w <= 0 or px_h <= 0:
                continue
            ratio = max(px_w / px_h, px_h / px_w)
            if ratio > max_ratio:
                issues.append(
                    Issue(
                        "aspect_ratio",
                        WARN,
                        "BOX_ASPECT_RATIO_EXTREME",
                        p.stem,
                        f"dòng {i}: tỉ lệ cạnh {ratio:.1f} vượt ngưỡng {max_ratio}",
                        line=i,
                        extra={"ratio": round(ratio, 2)},
                    )
                )
    return issues
