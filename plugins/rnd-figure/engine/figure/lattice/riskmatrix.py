# -*- coding: utf-8 -*-
"""위험도 매트릭스 — 가능성 × 심각도 2차원 격자에 위험요인 배치.

칸 등급은 신호등 색을 쓰지 않고 **무채색 램프**로 표현한다.
흑백 인쇄에서 살아남아야 하고, 색이 판정을 대신하면 안 되기 때문이다.

한 칸에 여러 위험요인이 오면 위에서부터 칩(chip)으로 쌓는다.
칸에 안 들어가면 글자를 줄여 억지로 우겨넣지 않고 **적발**한다.
"""
from __future__ import annotations

from . import shapes
from .textbox import fit_text


def _idx(v, ticks, axis):
    """눈금 라벨('중') 또는 1-기반 번호(2) 를 0-기반 인덱스로."""
    if isinstance(v, str) and v in ticks:
        return ticks.index(v)
    try:
        i = int(v) - 1
    except (TypeError, ValueError):
        raise ValueError(f"{axis} 값 '{v}' 를 눈금 {ticks} 에서 찾을 수 없다")
    if not 0 <= i < len(ticks):
        raise ValueError(f"{axis} 값 '{v}' 가 눈금 범위 밖이다 (1~{len(ticks)})")
    return i


def render(ax, spec, t, cc, fitter):
    a = spec.get("area", {})
    L, R = float(a.get("left", 0.03)), float(a.get("right", 0.98))
    B, T = float(a.get("bottom", 0.04)), float(a.get("top", 0.97))

    # 축 정의는 x_axis/y_axis 다. 항목의 x/y(칸 좌표)와 이름이 겹치면
    # 스펙을 읽는 사람이 반드시 헷갈린다.
    xa = spec.get("x_axis") or {}
    ya = spec.get("y_axis") or {}
    xt = list(xa.get("ticks", ["저", "중", "상"]))
    yt = list(ya.get("ticks", ["저", "중", "상"]))
    nx, ny = len(xt), len(yt)

    axw = float(spec.get("axis_label_w", 0.040))
    tkw = float(spec.get("tick_w", 0.052))
    axh = float(spec.get("axis_label_h", 0.055))
    tkh = float(spec.get("tick_h", 0.052))
    gx0, gy0 = L + axw + tkw, B + axh + tkh
    cw, ch = (R - gx0) / nx, (T - gy0) / ny

    # ── 칸 음영 ──────────────────────────────────────────────
    nz = len(t.zones) - 1
    for i in range(nx):
        for j in range(ny):
            fx = i / (nx - 1) if nx > 1 else 0.0
            fy = j / (ny - 1) if ny > 1 else 0.0
            lv = int(round((fx + fy) / 2 * nz))
            shapes.box(ax, (gx0 + i * cw, gy0 + j * ch,
                            gx0 + (i + 1) * cw, gy0 + (j + 1) * ch),
                       fill=t.zones[lv], edge=t.grid, lw=t.lw_grid, zorder=1)
    shapes.box(ax, (gx0, gy0, R, T), fill="none", edge=t.outline,
               lw=t.lw_box, zorder=2)

    # ── 눈금 · 축 이름 ───────────────────────────────────────
    for i, s in enumerate(xt):
        tt = ax.text(gx0 + (i + 0.5) * cw, gy0 - tkh / 2, str(s), ha="center",
                     va="center", fontsize=t.fs_head, fontweight="bold",
                     color=t.text)
        cc.add_text(tt, f"가로눈금 {s}", owner=None)
    for j, s in enumerate(yt):
        tt = ax.text(gx0 - tkw / 2, gy0 + (j + 0.5) * ch, str(s), ha="center",
                     va="center", fontsize=t.fs_head, fontweight="bold",
                     color=t.text)
        cc.add_text(tt, f"세로눈금 {s}", owner=None)
    if xa.get("label"):
        tt = ax.text((gx0 + R) / 2, B + axh / 2, xa["label"], ha="center",
                     va="center", fontsize=t.fs_title, fontweight="bold",
                     color=t.text)
        cc.add_text(tt, xa["label"], owner=None)
    if ya.get("label"):
        tt = ax.text(L + axw / 2, (gy0 + T) / 2, ya["label"], ha="center",
                     va="center", fontsize=t.fs_title, fontweight="bold",
                     color=t.text, rotation=90)
        cc.add_text(tt, ya["label"], owner=None)

    # 방향 화살표는 기본 꺼 둔다. 눈금(저·중·상)이 이미 방향을 말하고 있고,
    # 축선과 겹쳐 그려져 흑백 인쇄에서 지저분해진다(실측).
    if spec.get("arrows", False):
        ax.annotate("", xy=(R, gy0 - tkh * 0.06), xytext=(gx0, gy0 - tkh * 0.06),
                    arrowprops=dict(arrowstyle="-|>", color=t.grid,
                                    lw=t.lw_grid, shrinkA=0, shrinkB=0))
        ax.annotate("", xy=(gx0 - tkw * 0.06, T), xytext=(gx0 - tkw * 0.06, gy0),
                    arrowprops=dict(arrowstyle="-|>", color=t.grid,
                                    lw=t.lw_grid, shrinkA=0, shrinkB=0))

    # ── 칩 배치 ─────────────────────────────────────────────
    cells: dict[tuple[int, int], list] = {}
    for it in spec.get("items", []):
        i = _idx(it.get("x"), xt, "x(가능성)")
        j = _idx(it.get("y"), yt, "y(심각도)")
        cells.setdefault((i, j), []).append(it)

    pad_x = cw * float(spec.get("chip_pad_x", 0.06))
    pad_y = ch * float(spec.get("chip_pad_y", 0.07))
    hmax = ch * float(spec.get("chip_h_max", 0.40))
    for (i, j), group in sorted(cells.items()):
        k = len(group)
        x0 = gx0 + i * cw + pad_x
        x1 = gx0 + (i + 1) * cw - pad_x
        avail = ch - pad_y * 2
        gap = pad_y * 0.6
        # 칩 높이에 상한을 둔다. 항목이 하나뿐인 칸에서 칩이 칸을 통째로
        # 차지하면 다른 칸과 크기가 달라 보여 격자가 아니라 상자 나열이 된다.
        h = max(min((avail - gap * (k - 1)) / k, hmax), ch * 0.04)
        # 위에서부터가 아니라 칸 중앙 기준으로 쌓는다
        total = k * h + gap * (k - 1)
        top = gy0 + (j + 0.5) * ch + total / 2
        for m, it in enumerate(group):
            y1 = top - m * (h + gap)
            rect = (x0, y1 - h, x1, y1)
            shapes.box(ax, rect, fill="#FFFFFF", edge=t.outline,
                       lw=t.lw_box, zorder=4)
            key = f"chip{i}{j}_{m}"
            cc.add_box(key, rect)
            tt, ok = fit_text(ax, fitter, rect, it["label"], t,
                              fs=it.get("fs", t.fs_row), zorder=7)
            cc.add_text(tt, it["label"].replace("\n", " "), owner=key, fitted=ok)
