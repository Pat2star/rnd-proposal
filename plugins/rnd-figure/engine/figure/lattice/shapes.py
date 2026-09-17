# -*- coding: utf-8 -*-
"""격자 그림의 기본 도형 — 상자와 직교 연결선.

곡선·그림자·그러데이션을 쓰지 않는다. 인쇄 흑백 복사에서 무너지기 때문이다.
"""
from __future__ import annotations

from matplotlib.patches import FancyArrowPatch, Polygon, Rectangle


def box(ax, rect, fill="#FFFFFF", edge="#1A1A1A", lw=1.3, ls="solid", zorder=3,
        hatch=None):
    """rect = (x0, y0, x1, y1) → 사각형. 반환은 같은 형식의 bbox."""
    x0, y0, x1, y1 = rect
    p = Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=fill, edgecolor=edge,
                  linewidth=lw, linestyle=ls, zorder=zorder, hatch=hatch)
    ax.add_patch(p)
    return (x0, y0, x1, y1)


def anchors(rect):
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return {"left": (x0, cy), "right": (x1, cy), "top": (cx, y1),
            "bottom": (cx, y0), "center": (cx, cy), "bbox": rect}


def _poly(ax, pts, color, lw, ls, zorder):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ax.plot(xs, ys, color=color, lw=lw, linestyle=ls, zorder=zorder,
            solid_capstyle="round", solid_joinstyle="miter")


def connect(ax, a, b, route="VHV", color="#1A1A1A", lw=1.1, ls="solid",
            zorder=2, arrow=False, mid=None):
    """직교 연결선. a, b 는 anchors() 결과.

    VHV  부모 아래 → 중간 높이 → 자식 위      (계층 조직도의 기본)
    HVH  좌우 → 중간 폭 → 좌우
    H    같은 높이로 직행 (좌우 근접 상자)
    V    같은 x 로 직행
    """
    if route == "H":
        p0 = a["right"] if a["center"][0] <= b["center"][0] else a["left"]
        p1 = b["left"] if a["center"][0] <= b["center"][0] else b["right"]
        pts = [p0, p1]
    elif route == "V":
        down = a["center"][1] > b["center"][1]
        p0 = a["bottom"] if down else a["top"]
        p1 = b["top"] if down else b["bottom"]
        pts = [p0, p1]
    elif route == "HVH":
        p0 = a["right"] if a["center"][0] <= b["center"][0] else a["left"]
        p1 = b["left"] if a["center"][0] <= b["center"][0] else b["right"]
        xm = mid if mid is not None else (p0[0] + p1[0]) / 2
        pts = [p0, (xm, p0[1]), (xm, p1[1]), p1]
    else:                                            # VHV
        down = a["center"][1] > b["center"][1]
        p0 = a["bottom"] if down else a["top"]
        p1 = b["top"] if down else b["bottom"]
        ym = mid if mid is not None else (p0[1] + p1[1]) / 2
        pts = [p0, (p0[0], ym), (p1[0], ym), p1]

    if arrow:
        _poly(ax, pts[:-1], color, lw, ls, zorder)
        ax.add_patch(FancyArrowPatch(
            pts[-2], pts[-1], arrowstyle="-|>", mutation_scale=9,
            color=color, lw=lw, linestyle=ls, zorder=zorder,
            shrinkA=0, shrinkB=0))
    else:
        _poly(ax, pts, color, lw, ls, zorder)
    return pts


def diamond(ax, x, y, rx, ry, fill="#1A1A1A", edge="#1A1A1A", lw=1.0, zorder=5):
    ax.add_patch(Polygon([(x, y + ry), (x + rx, y), (x, y - ry), (x - rx, y)],
                         closed=True, facecolor=fill, edgecolor=edge,
                         linewidth=lw, zorder=zorder))
