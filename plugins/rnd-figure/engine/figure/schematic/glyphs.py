# -*- coding: utf-8 -*-
"""공학 부품 글리프 — 앵커를 돌려주는 것이 핵심.

목표 기준은 사용자가 PowerPoint로 직접 만든 Fig1_schematic.png 다.
(AI가 만든 18KB matplotlib 폴백이 아니다 — 그건 상태점·그룹박스·온도배지를
붙여 과잉 장식했다. 실제 문법은 훨씬 미니멀하다.)

실측한 문법:
  압축기  사다리꼴 좌변 높음 → 우변 낮음 (면적 축소) + 파랑→주황 그라디언트
  팽창기  사다리꼴 좌변 낮음 → 우변 높음 (면적 확대) + 주황→파랑
  열교환기 연노랑 사각형 + W자 지그재그 + 굵은 검정 테두리
  밸브    나비넥타이, 회색 채움
  모터    작은 원 + 이니셜
  축      압축기↔팽창기 사이 회색 굵은 수평 바

**모든 글리프는 앵커 dict를 돌려준다.** 좌표 하드코딩을 없애는 유일한 방법이다.
(참고: AI 폴백의 v1에는 앵커가 있었는데 v2에서 제거되고 좌표 하드코딩으로
퇴화했다. 그게 그 스크립트의 가장 큰 설계 후퇴였다.)
"""
from __future__ import annotations

import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Circle, Ellipse, Polygon, Rectangle


def _anchors(cx, cy, w, h, extra=None):
    a = {
        "center": (cx, cy),
        "left": (cx - w / 2, cy), "right": (cx + w / 2, cy),
        "top": (cx, cy + h / 2), "bottom": (cx, cy - h / 2),
        "bbox": (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2),
    }
    a["in"], a["out"] = a["left"], a["right"]
    if extra:
        a.update(extra)
    return a


def _gradient_fill(ax, verts, c_left, c_right, zorder=3):
    """다각형 안을 좌→우 선형 그라디언트로 채운다.

    matplotlib에는 폴리곤 그라디언트가 없어서 imshow를 클립한다.
    """
    verts = np.asarray(verts)
    x0, x1 = verts[:, 0].min(), verts[:, 0].max()
    y0, y1 = verts[:, 1].min(), verts[:, 1].max()
    cmap = LinearSegmentedColormap.from_list("g", [c_left, c_right])
    grad = np.linspace(0, 1, 256).reshape(1, -1)
    im = ax.imshow(grad, extent=(x0, x1, y0, y1), aspect="auto",
                   cmap=cmap, zorder=zorder, interpolation="bilinear")
    clip = Polygon(verts, closed=True, transform=ax.transData)
    im.set_clip_path(clip)
    return im


def compressor(ax, cx, cy, w, h, label="Comp", theme=None, taper=0.28):
    """좌변 높고 우변 낮은 사다리꼴 = 면적 축소 = 압축."""
    t = theme
    dy = taper * h
    verts = [(cx - w / 2, cy + h / 2), (cx + w / 2, cy + h / 2 - dy),
             (cx + w / 2, cy - h / 2 + dy), (cx - w / 2, cy - h / 2)]
    _gradient_fill(ax, verts, t.cool, t.hot)
    ax.add_patch(Polygon(verts, closed=True, facecolor="none",
                         edgecolor=t.outline, linewidth=t.lw_component, zorder=4))
    return _anchors(cx, cy, w, h, {
        "label": label, "kind": "compressor",
        "shaft": (cx + w / 2, cy),
        "verts": verts,
    })


def expander(ax, cx, cy, w, h, label="Exp", theme=None, taper=0.28):
    """좌변 낮고 우변 높은 사다리꼴 = 면적 확대 = 팽창."""
    t = theme
    dy = taper * h
    verts = [(cx - w / 2, cy + h / 2 - dy), (cx + w / 2, cy + h / 2),
             (cx + w / 2, cy - h / 2), (cx - w / 2, cy - h / 2 + dy)]
    _gradient_fill(ax, verts, t.hot, t.cool)
    ax.add_patch(Polygon(verts, closed=True, facecolor="none",
                         edgecolor=t.outline, linewidth=t.lw_component, zorder=4))
    return _anchors(cx, cy, w, h, {
        "label": label, "kind": "expander",
        "shaft": (cx - w / 2, cy),
        "verts": verts,
    })


turbine = expander          # 별칭


def hx(ax, cx, cy, w, h, label="HX", theme=None, peaks=3):
    """연노랑 사각형 + W자 지그재그. 열교환기."""
    t = theme
    ax.add_patch(Rectangle((cx - w / 2, cy - h / 2), w, h,
                           facecolor=t.hx_fill, edgecolor=t.outline,
                           linewidth=t.lw_component, zorder=3))
    # 지그재그 — 좌우 여백 12%, 위아래 진폭 30%
    pad = w * 0.12
    n = peaks * 2
    xs = np.linspace(cx - w / 2 + pad, cx + w / 2 - pad, n + 1)
    amp = h * 0.30
    ys = [cy + (amp if i % 2 == 0 else -amp) for i in range(n + 1)]
    ax.plot(xs, ys, color=t.outline, linewidth=t.lw_zigzag,
            solid_joinstyle="miter", zorder=4)
    return _anchors(cx, cy, w, h, {"label": label, "kind": "hx"})


def valve(ax, cx, cy, size, label="VLV", theme=None):
    """나비넥타이. 팽창밸브."""
    t = theme
    s = size / 2
    left = [(cx - s, cy + s), (cx - s, cy - s), (cx, cy)]
    right = [(cx + s, cy + s), (cx + s, cy - s), (cx, cy)]
    for v in (left, right):
        ax.add_patch(Polygon(v, closed=True, facecolor=t.valve_fill,
                             edgecolor=t.outline, linewidth=t.lw_component,
                             zorder=4))
    return _anchors(cx, cy, size, size, {"label": label, "kind": "valve"})


def _data_aspect(ax) -> float:
    """축의 데이터 1단위가 화면에서 가로:세로 몇 배인가.

    ★ 패널은 0..1 정규좌표를 패널 상자에 꽉 채운다(aspect 사실상 auto —
    _gradient_fill의 imshow(aspect="auto")가 set_aspect("equal")을 덮는다).
    그래서 반지름이 같은 Circle이 화면에서는 타원이 된다. 실측: hero 캔버스
    (3200x2000, 1x1 그리드)에서 모터가 눈에 띄게 가로로 늘어났다.
    """
    bb = ax.get_window_extent()
    xs = ax.get_xlim(); ys = ax.get_ylim()
    dx = (xs[1] - xs[0]) or 1.0
    dy = (ys[1] - ys[0]) or 1.0
    return (bb.width / dx) / (bb.height / dy)


def motor(ax, cx, cy, r, label="M", theme=None):
    """작은 원 + 이니셜. 모터/제너레이터."""
    t = theme
    # 화면에서 정원으로 보이도록 가로 반지름을 축 비율로 나눈다.
    ar = _data_aspect(ax)
    ax.add_patch(Ellipse((cx, cy), 2 * r / ar, 2 * r, facecolor=t.surface,
                         edgecolor=t.outline, linewidth=t.lw_component,
                         zorder=5))
    ax.text(cx, cy, label, ha="center", va="center",
            fontsize=t.fs_glyph_small, fontweight="bold",
            color=t.outline, zorder=6)
    return _anchors(cx, cy, 2 * r, 2 * r, {"label": None, "kind": "motor"})


def shaft(ax, a_anchor, b_anchor, theme=None, thickness=None):
    """압축기 ↔ 팽창기를 잇는 회색 굵은 수평 바."""
    t = theme
    x0, y0 = a_anchor["shaft"] if "shaft" in a_anchor else a_anchor["right"]
    x1, y1 = b_anchor["shaft"] if "shaft" in b_anchor else b_anchor["left"]
    th = thickness if thickness is not None else t.shaft_thickness
    y = (y0 + y1) / 2
    ax.add_patch(Rectangle((min(x0, x1), y - th / 2), abs(x1 - x0), th,
                           facecolor=t.shaft_fill, edgecolor=t.outline,
                           linewidth=t.lw_thin, zorder=2))
    return {"center": ((x0 + x1) / 2, y),
            "bbox": (min(x0, x1), y - th / 2, max(x0, x1), y + th / 2)}


GLYPHS = {
    "compressor": compressor, "expander": expander, "turbine": turbine,
    "hx": hx, "valve": valve, "motor": motor, "generator": motor,
}
