"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |
"""
from collections import defaultdict
from pathlib import Path

import yaml

from ..common import ERROR, parse_yolo_line

IMAGE_REMOVE_CODES = {
    "DUP_IMAGE_EXACT",
    "DUP_IMAGE_NEAR",
    "LEAK_TEST",
    "CORRUPT_IMAGE",
    "BAD_SIZE",
}

DROP_LINE_CODES = {
    "BAD_FORMAT",
    "BAD_CLASS_ID",
    "BOX_ZERO",
    "DUP_BOX",
}


def fix(ds, issues, cfg):
    # Chỉ xử lý các lỗi có severity == ERROR
    error_issues = [i for i in issues if i.severity == ERROR]
    fixes = []

    # 1. BAD_CLASS_NAME (Cấp data.yaml)
    yaml_issues = [i for i in error_issues if i.code == "BAD_CLASS_NAME"]
    if yaml_issues and ds.yaml_path.exists():
        try:
            data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        old_names = data.get("names", [])
        data["names"] = list(cfg["classes"])
        ds.yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        fixes.append({
            "image": "data.yaml",
            "line": "",
            "action": "rename_classes",
            "before": str(old_names),
            "after": str(cfg["classes"]),
        })

    # 2. Xóa ảnh và nhãn (remove_image)
    removed_images = set()
    remove_img_issues = [i for i in error_issues if i.code in IMAGE_REMOVE_CODES]
    for iss in remove_img_issues:
        stem = iss.image
        if stem in removed_images:
            continue
        removed_images.add(stem)

        # Xóa file ảnh
        img_p = ds.image_path(stem)
        if img_p and img_p.exists():
            img_p.unlink()

        # Xóa file nhãn nếu có
        lbl_p = ds.label_path(stem)
        if lbl_p and lbl_p.exists():
            lbl_p.unlink()

        fixes.append({
            "image": stem,
            "line": "",
            "action": "remove_image",
            "before": iss.message,
            "after": "đã xoá ảnh và nhãn",
        })

    # 3. MISSING_LABEL_FILE -> needs_label (không tạo file nhãn)
    missing_lbl_issues = [i for i in error_issues if i.code == "MISSING_LABEL_FILE"]
    for iss in missing_lbl_issues:
        if iss.image in removed_images:
            continue
        fixes.append({
            "image": iss.image,
            "line": "",
            "action": "needs_label",
            "before": "(không có file)",
            "after": "chuyển người gán",
        })

    # 4. Sửa cấp dòng nhãn trong file txt
    # Gom issues theo stem
    line_issues_by_stem = defaultdict(lambda: defaultdict(list))
    for iss in error_issues:
        if iss.image in removed_images:
            continue
        if iss.line is not None and (iss.code in DROP_LINE_CODES or iss.code == "BOX_OUT_OF_IMAGE"):
            line_issues_by_stem[iss.image][iss.line].append(iss)

    for stem, lines_dict in line_issues_by_stem.items():
        lbl_p = ds.label_path(stem)
        if not lbl_p.exists():
            continue

        raw_lines = lbl_p.read_text(encoding="utf-8", errors="replace").splitlines()
        dropped_lines = set()
        modified_lines = {}  # 1-based line_no -> new_line_str

        # Duyệt từng dòng lỗi (sắp xếp theo số dòng gốc)
        for line_no in sorted(lines_dict.keys()):
            if line_no < 1 or line_no > len(raw_lines):
                continue

            cur_raw = raw_lines[line_no - 1]
            issues_on_line = lines_dict[line_no]

            # Nếu có bất kỳ lỗi nào thuộc DROP_LINE_CODES -> drop_line thắng
            has_drop = any(i.code in DROP_LINE_CODES for i in issues_on_line)
            if has_drop:
                dropped_lines.add(line_no)
                fixes.append({
                    "image": stem,
                    "line": line_no,
                    "action": "drop_line",
                    "before": cur_raw,
                    "after": "",
                })
                continue

            # Nếu có lỗi BOX_OUT_OF_IMAGE
            has_overflow = any(i.code == "BOX_OUT_OF_IMAGE" for i in issues_on_line)
            if has_overflow:
                try:
                    c, x, y, w, h = parse_yolo_line(cur_raw)
                    x1 = x - w / 2.0
                    x2 = x + w / 2.0
                    y1 = y - h / 2.0
                    y2 = y + h / 2.0

                    # Cắt về trong [0, 1]
                    cx1 = max(0.0, min(1.0, x1))
                    cx2 = max(0.0, min(1.0, x2))
                    cy1 = max(0.0, min(1.0, y1))
                    cy2 = max(0.0, min(1.0, y2))

                    nw = cx2 - cx1
                    nh = cy2 - cy1

                    # Nếu sau khi cắt diện tích <= 0 (nằm hẳn ngoài ảnh) -> drop_line
                    if nw <= 0.0 or nh <= 0.0:
                        dropped_lines.add(line_no)
                        fixes.append({
                            "image": stem,
                            "line": line_no,
                            "action": "drop_line",
                            "before": cur_raw,
                            "after": "",
                        })
                    else:
                        nx = (cx1 + cx2) / 2.0
                        ny = (cy1 + cy2) / 2.0
                        new_line_str = f"{c} {nx:.6f} {ny:.6f} {nw:.6f} {nh:.6f}"
                        modified_lines[line_no] = new_line_str
                        fixes.append({
                            "image": stem,
                            "line": line_no,
                            "action": "clip_box",
                            "before": cur_raw,
                            "after": new_line_str,
                        })
                except ValueError:
                    # Nếu parse lỗi thì drop_line
                    dropped_lines.add(line_no)
                    fixes.append({
                        "image": stem,
                        "line": line_no,
                        "action": "drop_line",
                        "before": cur_raw,
                        "after": "",
                    })

        # Ghi lại nội dung file nhãn
        new_raw_lines = []
        for idx, line_str in enumerate(raw_lines, 1):
            if idx in dropped_lines:
                continue
            if idx in modified_lines:
                new_raw_lines.append(modified_lines[idx])
            else:
                new_raw_lines.append(line_str)

        out_content = "\n".join(new_raw_lines) + ("\n" if new_raw_lines else "")
        lbl_p.write_text(out_content, encoding="utf-8")

    return fixes
