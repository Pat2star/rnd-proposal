# -*- coding: utf-8 -*-
"""포트 기반 직각(Manhattan) 배관 라우팅.

AI 폴백 스크립트는 꺾임점 리스트를 손으로 넘겨야 했다. 그래서 HX 폭을 바꾸면
배관이 즉시 어긋났다. 여기서는 **앵커 두 개만 주면 경로를 자동 생성**한다.
"""
from __future__ import annotations

from matplotlib.patches import FancyArrowPatch

DASH = {"solid": (None, None), "dashed": (0, (5, 3))}


def _route(p0, p1, mode="auto", detour=None):
    """직각 경로 꺾임점 리스트."""
    x0, y0 = p0
    x1, y1 = p1
    if abs(y1 - y0) < 1e-9 or abs(x1 - x0) < 1e-9:
        return [p0, p1]
    if mode == "auto":
        mode = "HV" if abs(x1 - x0) >= abs(y1 - y0) else "VH"
    if mode == "HV":
        return [p0, (x1, y0), p1]
    if mode == "VH":
        return [p0, (x0, y1), p1]
    if mode == "HVH":
        mx = detour if detour is not None else (x0 + x1) / 2
        return [p0, (mx, y0), (mx, y1), p1]
    if mode == "VHV":
        my = detour if detour is not None else (y0 + y1) / 2
        return [p0, (x0, my), (x1, my), p1]
    return [p0, p1]


def pipe(ax, p0, p1, theme, fluid="primary", mode="auto", detour=None,
         arrow=True, zorder=2, lw=None):
    """앵커 좌표 두 개 → 직각 배관 + 끝 화살촉."""
    f = theme.fluids.get(fluid, theme.fluids["primary"])
    pts = _route(p0, p1, mode, detour)
    color = f["color"]
    ls = DASH.get(f["style"], (None, None))
    lw = lw if lw is not None else theme.lw_stream

    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        last = (i == len(pts) - 2)
        if last and arrow:
            ax.add_patch(FancyArrowPatch(
                a, b, arrowstyle="-|>", mutation_scale=11,
                color=color, linewidth=lw,
                linestyle=ls if ls[0] is not None else "solid",
                shrinkA=0, shrinkB=0, zorder=zorder,
                joinstyle="miter", capstyle="butt"))
        else:
            ax.plot([a[0], b[0]], [a[1], b[1]], color=color, linewidth=lw,
                    linestyle=(ls if ls[0] is not None else "-"),
                    solid_capstyle="projecting", zorder=zorder)
    return pts


def heat_stub(ax, anchor, theme, fluid="heat_sink", direction="up",
              length=0.10, label=None, label_side="left", fs=None,
              dx=0.0, into=False):
    """열원/열침 화살표 — 부품 옆의 짧은 점선 + 라벨.

    실측 문법: 'Heat sink'는 위로 파란 점선, 'Heat source'는 아래로 빨간 점선.
    한 쌍(들어오고 나가는)으로 그리는 게 원본 관행이다.

    ``into=True`` 면 화살촉을 **부품 쪽으로** 돌린다. 열이 들어오는 쪽
    (증발기의 폐열, 보일러의 열원)은 이게 물리적으로 맞다. 기본값 False는
    기존 스펙의 그림을 바꾸지 않기 위한 것이다.
    """
    x, y = anchor
    x += dx                     # 중앙 라벨과 겹치지 않게 옆으로 비킨다
    dy = length if direction == "up" else -length
    f = theme.fluids[fluid]
    ls = DASH.get(f["style"], (None, None))
    a, b = ((x, y + dy), (x, y)) if into else ((x, y), (x, y + dy))
    ax.add_patch(FancyArrowPatch(
        a, b, arrowstyle="-|>", mutation_scale=10,
        color=f["color"], linewidth=theme.lw_stream,
        linestyle=ls if ls[0] is not None else "solid",
        shrinkA=0, shrinkB=0, zorder=2))
    tip = (x, y + dy)
    if label:
        ha = "right" if label_side == "left" else "left"
        ox = -0.012 if label_side == "left" else 0.012
        ax.text(tip[0] + ox, tip[1], label, ha=ha, va="center",
                fontsize=fs or theme.fs_stream, fontweight="bold",
                color=theme.text, zorder=6)
    return tip
