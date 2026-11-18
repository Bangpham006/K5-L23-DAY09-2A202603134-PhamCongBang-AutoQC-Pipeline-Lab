"""Kiểm thử unit test cho check thưởng — tỉ lệ khung hình bất thường (aspect ratio extreme)."""
from pipeline.checks import aspect_ratio


def test_normal_aspect_ratio_passes(make_ds, cfg):
    # Box thông thường: 0.2 x 0.1 (tỉ lệ 2.0 trên ảnh 320x240) -> không cảnh báo
    ds = make_ds(images={"img1": 1}, labels={"img1": ["0 0.5 0.5 0.2 0.1"]})
    issues = aspect_ratio.run(ds, cfg)
    assert len(issues) == 0


def test_extreme_horizontal_aspect_ratio_warns(make_ds, cfg):
    # Box cực dẹt theo chiều ngang: w=0.8, h=0.01 trên ảnh 320x240
    # w_px = 256, h_px = 2.4 -> ratio = 106.7 > 10 -> phải cảnh báo
    ds = make_ds(images={"img2": 1}, labels={"img2": ["0 0.5 0.5 0.8 0.01"]})
    issues = aspect_ratio.run(ds, cfg)
    assert len(issues) == 1
    assert issues[0].code == "BOX_ASPECT_RATIO_EXTREME"
    assert issues[0].line == 1
    assert issues[0].extra["ratio"] > 10.0


def test_extreme_vertical_aspect_ratio_warns(make_ds, cfg):
    # Box cực mảnh theo chiều dọc: w=0.01, h=0.8 trên ảnh 320x240
    # w_px = 3.2, h_px = 192 -> ratio = 60.0 > 10 -> phải cảnh báo
    ds = make_ds(images={"img3": 1}, labels={"img3": ["1 0.5 0.5 0.01 0.8"]})
    issues = aspect_ratio.run(ds, cfg)
    assert len(issues) == 1
    assert issues[0].code == "BOX_ASPECT_RATIO_EXTREME"
    assert issues[0].line == 1


def test_custom_threshold_from_cfg(make_ds, cfg):
    # Ngưỡng tùy chỉnh là 5.0; box có ratio = 6.0 sẽ bị bắt
    cfg["aspect_ratio"] = {"max_ratio": 5.0}
    # Trên ảnh 320x240, w=0.3 -> 96px, h=0.05 -> 12px -> ratio = 8.0
    ds = make_ds(images={"img4": 1}, labels={"img4": ["0 0.5 0.5 0.3 0.05"]})
    issues = aspect_ratio.run(ds, cfg)
    assert len(issues) == 1
    assert issues[0].code == "BOX_ASPECT_RATIO_EXTREME"


def test_skips_invalid_lines_and_missing_labels(make_ds, cfg):
    ds = make_ds(images={"img5": 1, "img6": 2}, labels={"img5": ["0 0.5 0.5", "nan inf 0.1 0.2 0.3"]})
    issues = aspect_ratio.run(ds, cfg)
    assert len(issues) == 0
