"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line


def run(ds, cfg):
    lf_cfg = cfg.get("label_format", {})
    overflow_tol = lf_cfg.get("overflow_tol", 0.002)
    min_box_px = lf_cfg.get("min_box_px", 12)
    max_box_frac = lf_cfg.get("max_box_frac", 0.95)
    dup_box_iou = lf_cfg.get("dup_box_iou", 0.9)

    num_classes = len(ds.classes)
    issues = []

    for p in ds.label_files():
        stem = p.stem
        lines = ds.read_label_lines(stem)
        if not lines:
            continue

        im_size = ds.image_size(stem)
        valid_boxes = []  # list of (line_no, c, current_box_xywh)

        for line_no, text in lines:
            # 1. Parse format
            try:
                c, x, y, w, h = parse_yolo_line(text)
            except ValueError as e:
                issues.append(
                    Issue("label_format", ERROR, "BAD_FORMAT", stem, f"sai định dạng dòng {line_no}: {e}", line=line_no)
                )
                continue

            # 2. Class ID
            if not (0 <= c < num_classes):
                issues.append(
                    Issue("label_format", ERROR, "BAD_CLASS_ID", stem, f"id lớp {c} ngoài phạm vi 0..{num_classes - 1}", line=line_no)
                )
                continue

            # 3. Box zero
            if w <= 0 or h <= 0:
                issues.append(
                    Issue("label_format", ERROR, "BOX_ZERO", stem, f"box rộng={w}, cao={h} <= 0", line=line_no)
                )
                continue

            # 4. Box out of image (overflow)
            x1 = x - w / 2.0
            x2 = x + w / 2.0
            y1 = y - h / 2.0
            y2 = y + h / 2.0

            o_left = max(0.0, -x1)
            o_top = max(0.0, -y1)
            o_right = max(0.0, x2 - 1.0)
            o_bottom = max(0.0, y2 - 1.0)
            overflow = max(o_left, o_top, o_right, o_bottom)

            if overflow > overflow_tol:
                issues.append(
                    Issue(
                        "label_format",
                        ERROR,
                        "BOX_OUT_OF_IMAGE",
                        stem,
                        f"box tràn ra ngoài ảnh: mức tràn {overflow:.4f} > {overflow_tol}",
                        line=line_no,
                        extra={"overflow": float(overflow)},
                    )
                )

            # 5. Duplicate box (compared to previously seen valid boxes of the same class)
            current_box_xywh = (x, y, w, h)
            for prev_line, prev_c, prev_xywh in valid_boxes:
                if c == prev_c and iou_xywh(current_box_xywh, prev_xywh) > dup_box_iou:
                    issues.append(
                        Issue(
                            "label_format",
                            ERROR,
                            "DUP_BOX",
                            stem,
                            f"trùng với dòng {prev_line} (IoU > {dup_box_iou})",
                            line=line_no,
                            extra={"of_line": prev_line},
                        )
                    )
                    break

            valid_boxes.append((line_no, c, current_box_xywh))

            # 6. Box tiny (Warning)
            if im_size:
                im_w, im_h = im_size
                short_side_px = min(w * im_w, h * im_h)
                if short_side_px < min_box_px:
                    issues.append(
                        Issue(
                            "label_format",
                            WARN,
                            "BOX_TINY",
                            stem,
                            f"cạnh ngắn {short_side_px:.1f}px < {min_box_px}px",
                            line=line_no,
                            extra={"short_side_px": float(short_side_px)},
                        )
                    )

            # 7. Box huge (Warning)
            box_area_frac = w * h
            if box_area_frac > max_box_frac:
                issues.append(
                    Issue(
                        "label_format",
                        WARN,
                        "BOX_HUGE",
                        stem,
                        f"diện tích box {box_area_frac:.3f} > {max_box_frac}",
                        line=line_no,
                        extra={"frac": float(box_area_frac)},
                    )
                )

    return issues
