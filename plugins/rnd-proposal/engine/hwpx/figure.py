# -*- coding: utf-8 -*-
"""PNG 계측 → hp:pic 기하.

공식 (docs/hwpx_format_notes.md §8, 독립 2건 교차검증):
    imgDim = px × 75                    # 75 = 7200/96, 항상 96 DPI 기준
    orgSz  = px × 7200 / dpi            # PNG에 기록된 DPI. 기본은 무시하고 96
    curSz = sz = orgSz × scale          # scale = min(1, max_width / orgSz.w)
    scaMatrix.e1 = curSz.w / orgSz.w

⚠️ matplotlib savefig(dpi=300)은 PNG에 300dpi를 기록한다 → orgSz가 작아져
   그림이 작게 박힌다. 그래서 **dpi를 무시하고 96 고정이 기본값**이다.
"""
from __future__ import annotations

import os

from .consts import HWPUNIT_PER_INCH, HWPUNIT_PER_PX96


def png_size(path: str) -> tuple[int, int, int | None]:
    """(width_px, height_px, dpi_or_None) — PIL 없이 PNG 헤더만 읽어도 되지만
    PIL이 이미 의존성이므로 그냥 쓴다 (JPEG 등도 처리)."""
    from PIL import Image
    with Image.open(path) as im:
        w, h = im.size
        dpi = im.info.get("dpi")
        d = int(round(dpi[0])) if dpi and dpi[0] else None
    return w, h, d


def geometry(path: str, max_width: int, respect_dpi: bool = False,
             width_pct: float = 1.0) -> dict:
    px_w, px_h, png_dpi = png_size(path)
    dpi = png_dpi if (respect_dpi and png_dpi) else 96

    org_w = round(px_w * HWPUNIT_PER_INCH / dpi)
    org_h = round(px_h * HWPUNIT_PER_INCH / dpi)
    dim_w = px_w * HWPUNIT_PER_PX96
    dim_h = px_h * HWPUNIT_PER_PX96

    target = round(max_width * width_pct)
    scale = min(1.0, target / org_w) if org_w else 1.0
    cur_w = round(org_w * scale)
    cur_h = round(org_h * scale)
    # 종횡비 보존 우선 — 반올림 오차로 AR이 틀어지면 높이를 다시 맞춘다
    if cur_w and abs(cur_w / max(cur_h, 1) - px_w / px_h) > 1e-3:
        cur_h = round(cur_w * px_h / px_w)

    return {
        "px": (px_w, px_h),
        "png_dpi": png_dpi,
        "orgSz": (org_w, org_h),
        "curSz": (cur_w, cur_h),
        "imgDim": (dim_w, dim_h),
        "scaMatrix": (cur_w / org_w if org_w else 1.0,
                      cur_h / org_h if org_h else 1.0),
        "aspect": px_w / px_h if px_h else 0.0,
        "file": os.path.basename(path),
    }
