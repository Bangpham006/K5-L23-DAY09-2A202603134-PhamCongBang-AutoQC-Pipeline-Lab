"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from __future__ import annotations

from ..common import WARN, Dataset, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


def run(ds: Dataset, cfg: dict, preds: dict | None = None) -> list[Issue]:
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    so_cfg = cfg.get("second_opinion", {})
    conf_th = float(so_cfg.get("conf", 0.25))
    min_area_px = float(so_cfg.get("min_area_px", 600))
    fp_conf = float(so_cfg.get("fp_conf", 0.1))
    iou_missing = float(so_cfg.get("iou_missing", 0.3))
    iou_match = float(so_cfg.get("iou_match", 0.5))
    iou_loose = float(so_cfg.get("iou_loose", 0.5))

    issues: list[Issue] = []

    for img_path in ds.image_files():
        stem = img_path.stem
        if stem not in preds:
            continue

        raw_lines = ds.read_label_lines(stem)
        if raw_lines is None:
            continue

        size = ds.image_size(stem)
        if size is None:
            continue
        img_w, img_h = size
        if img_w <= 0 or img_h <= 0:
            continue

        # Lọc các dòng nhãn hợp lệ (kèm số dòng gốc 1-based)
        valid_label_lines: list[tuple[int, tuple[int, float, float, float, float]]] = []
        for line_num, line_str in raw_lines:
            try:
                b = parse_yolo_line(line_str)
            except ValueError:
                continue
            if 0 <= b[0] < len(ds.classes):
                valid_label_lines.append((line_num, b))

        valid_boxes = [b for _, b in valid_label_lines]
        img_preds = preds.get(stem, [])

        # 1. Đánh giá từng dự đoán của model (theo thứ tự xuất hiện trong preds[stem])
        for r in img_preds:
            p_cls = int(r[0])
            p_conf = float(r[1])
            p_cx, p_cy, p_w, p_h = float(r[2]), float(r[3]), float(r[4]), float(r[5])
            p_box = (p_cx, p_cy, p_w, p_h)
            area_px = (p_w * img_w) * (p_h * img_h)

            # Lọc P: conf >= conf_th VÀ diện tích px >= min_area_px
            if p_conf < conf_th or area_px < min_area_px:
                continue

            # cands gồm nhãn MỌI lớp có IoU >= iou_missing
            cands = []
            for lbl in valid_boxes:
                iou = iou_xywh(p_box, (lbl[1], lbl[2], lbl[3], lbl[4]))
                if iou >= iou_missing:
                    cands.append((lbl[0], (lbl[1], lbl[2], lbl[3], lbl[4]), iou))

            if not cands:
                # (1) Không có cands -> POSSIBLE_MISSING
                cls_name = ds.classes[p_cls] if 0 <= p_cls < len(ds.classes) else str(p_cls)
                issues.append(
                    Issue(
                        check="second_opinion",
                        severity=WARN,
                        code="POSSIBLE_MISSING",
                        image=stem,
                        line=None,
                        message=f"Model phát hiện {cls_name} (conf={p_conf:.2f}) nhưng nhãn thiếu box",
                        extra={"conf": round(p_conf, 4)},
                    )
                )
            else:
                same_class = [c for c in cands if c[0] == p_cls]
                if same_class:
                    best_same = max(same_class, key=lambda c: c[2])
                    if best_same[2] < iou_loose:
                        cls_name = ds.classes[p_cls] if 0 <= p_cls < len(ds.classes) else str(p_cls)
                        issues.append(
                            Issue(
                                check="second_opinion",
                                severity=WARN,
                                code="POSSIBLE_LOOSE_BOX",
                                image=stem,
                                line=None,
                                message=f"Box nhãn {cls_name} lệch/lỏng so với model (IoU={best_same[2]:.2f})",
                                extra={"conf": round(p_conf, 4), "iou": round(best_same[2], 4)},
                            )
                        )
                    # ngược lại KHÔNG cờ (nhãn đúng lớp đã phủ vật này)
                else:
                    diff_class = [c for c in cands if c[0] != p_cls]
                    best_diff = max(diff_class, key=lambda c: c[2])
                    if best_diff[2] >= iou_match:
                        pred_cls_name = ds.classes[p_cls] if 0 <= p_cls < len(ds.classes) else str(p_cls)
                        lbl_cls_name = ds.classes[best_diff[0]] if 0 <= best_diff[0] < len(ds.classes) else str(best_diff[0])
                        issues.append(
                            Issue(
                                check="second_opinion",
                                severity=WARN,
                                code="POSSIBLE_WRONG_CLASS",
                                image=stem,
                                line=None,
                                message=f"Nhãn ghi {lbl_cls_name} nhưng model phát hiện {pred_cls_name} (conf={p_conf:.2f}, IoU={best_diff[2]:.2f})",
                                extra={"conf": round(p_conf, 4), "iou": round(best_diff[2], 4)},
                            )
                        )
                    # nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì

        # 2. Đánh giá POSSIBLE_FALSE_POS (với mỗi dòng nhãn hợp lệ, theo thứ tự số dòng)
        fp_preds = [r for r in img_preds if float(r[1]) >= fp_conf]

        for line_num, lbl_box in valid_label_lines:
            lbl_geom = (lbl_box[1], lbl_box[2], lbl_box[3], lbl_box[4])
            if not fp_preds:
                max_iou = 0.0
            else:
                max_iou = max(
                    (iou_xywh(lbl_geom, (float(r[2]), float(r[3]), float(r[4]), float(r[5]))) for r in fp_preds),
                    default=0.0,
                )

            if max_iou < iou_missing:
                lbl_cls = lbl_box[0]
                lbl_cls_name = ds.classes[lbl_cls] if 0 <= lbl_cls < len(ds.classes) else str(lbl_cls)
                issues.append(
                    Issue(
                        check="second_opinion",
                        severity=WARN,
                        code="POSSIBLE_FALSE_POS",
                        image=stem,
                        line=line_num,
                        message=f"Dòng {line_num}: Nhãn {lbl_cls_name} không khớp vật nào model phát hiện (max_iou={max_iou:.2f})",
                        extra={"max_iou": round(max_iou, 4)},
                    )
                )

    return issues
