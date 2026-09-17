# -*- coding: utf-8 -*-
"""진도표(간트) — 연차 × 세부과제 격자.

## 눈금 좌표계 (스펙에서 헷갈리면 안 되므로 못박는다)

    눈금 k = k차년도가 **시작하는** 지점.  마지막 눈금은 ncol+1.
    span: [1, 3]   → 1·2차년도 (2개 연차)
    span: [4, 4.2] → 4차년도 앞 10주 (1연차 = 1.0 이므로 10/52 ≈ 0.19)

연 단위 격자에 소수 눈금을 허용해 **주 단위 공정**(설치 10주·시운전 6주 등)을
같은 좌표계에서 표현한다. 별도 단위를 두지 않는 이유는, 단위가 둘이면
스펙을 읽는 사람이 매번 환산해야 하기 때문이다.
"""
from __future__ import annotations

from . import shapes
from .textbox import fit_text


def render(ax, spec, t, cc, fitter):
    a = spec.get("area", {})
    L, R = float(a.get("left", 0.02)), float(a.get("right", 0.98))
    B, T = float(a.get("bottom", 0.04)), float(a.get("top", 0.97))

    cols = list(spec.get("columns", []))
    if not cols:
        raise ValueError("진도표에 columns 가 없다")
    n = len(cols)
    notes = list(spec.get("column_notes", []) or [])
    rows = list(spec.get("rows", []))
    if not rows:
        raise ValueError("진도표에 rows 가 없다")

    labw = float(spec.get("label_width", 0.22)) * (R - L)
    px0, px1 = L + labw, R

    ph_h = float(spec.get("phase_h", 0.075)) if spec.get("phases") else 0.0
    hd_h = float(spec.get("header_h", 0.125 if notes else 0.085))
    gtop = T - ph_h - hd_h
    rowh = (gtop - B) / len(rows)

    def xof(k):
        return px0 + (float(k) - 1.0) / n * (px1 - px0)

    # ── 단계 밴드 ─────────────────────────────────────────────
    for i, p in enumerate(spec.get("phases", []) or []):
        s, e = p["span"]
        rect = (xof(s), T - ph_h, xof(e), T)
        shapes.box(ax, rect, fill=t.roles["group"]["fill"], edge=t.outline,
                   lw=t.lw_box)
        key = f"phase{i}"
        cc.add_box(key, rect)
        tt, ok = fit_text(ax, fitter, rect, p["label"], t, fs=t.fs_head,
                          weight="bold")
        cc.add_text(tt, p["label"], owner=key, fitted=ok)

    # ── 열 머리 (연차 + TRL 등 부기) ───────────────────────────
    head_lab = spec.get("corner", "세부 추진과제")
    crect = (L, gtop, L + labw, gtop + hd_h)
    shapes.box(ax, crect, fill="#FFFFFF", edge=t.outline, lw=t.lw_box)
    cc.add_box("corner", crect)
    tt, ok = fit_text(ax, fitter, crect, head_lab, t, fs=t.fs_head, weight="bold")
    cc.add_text(tt, head_lab, owner="corner", fitted=ok)

    for i, c in enumerate(cols):
        rect = (xof(i + 1), gtop, xof(i + 2), gtop + hd_h)
        shapes.box(ax, rect, fill="#FFFFFF", edge=t.outline, lw=t.lw_box)
        key = f"col{i}"
        cc.add_box(key, rect)
        note = notes[i] if i < len(notes) else None
        if note:
            ysep = rect[3] - (rect[3] - rect[1]) * 0.55
            ax.plot([rect[0], rect[2]], [ysep, ysep], color=t.grid,
                    lw=t.lw_grid, zorder=4)
            hb, bb = (rect[0], ysep, rect[2], rect[3]), (rect[0], rect[1], rect[2], ysep)
        else:
            hb, bb = rect, None
        tt, ok = fit_text(ax, fitter, hb, str(c), t, fs=t.fs_head, weight="bold")
        cc.add_text(tt, str(c), owner=key, fitted=ok)
        if bb is not None:
            tt, ok = fit_text(ax, fitter, bb, str(note), t, fs=t.fs_small)
            cc.add_text(tt, str(note), owner=key, fitted=ok)

    # ── 격자 ─────────────────────────────────────────────────
    for i in range(n + 1):
        x = xof(i + 1)
        ax.plot([x, x], [B, gtop], color=t.grid, lw=t.lw_grid, zorder=1)
    for i in range(len(rows) + 1):
        y = B + i * rowh
        ax.plot([L, R], [y, y], color=t.grid, lw=t.lw_grid, zorder=1)
    ax.plot([px0, px0], [B, gtop], color=t.outline, lw=t.lw_box, zorder=1)

    # ── 행 ───────────────────────────────────────────────────
    bar_frac = float(spec.get("bar_h", 0.42))
    for ri, row in enumerate(rows):
        y1 = gtop - ri * rowh
        y0 = y1 - rowh
        cy = (y0 + y1) / 2
        lrect = (L, y0, L + labw, y1)
        cc.add_box(f"row{ri}", lrect)
        tt, ok = fit_text(ax, fitter, lrect, row["label"], t,
                          fs=row.get("fs", t.fs_row), align="left",
                          pad=(0.90, 0.84))
        cc.add_text(tt, row["label"].replace("\n", " "), owner=f"row{ri}",
                    fitted=ok)

        bh = rowh * bar_frac
        for bi, bar in enumerate(row.get("bars", [])):
            s, e = bar["span"]
            rect = (xof(s), cy - bh / 2, xof(e), cy + bh / 2)
            st = t.bars.get(bar.get("style", "plain"), t.bars["plain"])
            shapes.box(ax, rect, fill=st["fill"], edge=st["edge"], lw=t.lw_box,
                       hatch=st["hatch"], zorder=3)
            key = f"bar{ri}_{bi}"
            cc.add_box(key, rect)
            lab = bar.get("label")
            if lab:
                tt, ok = fit_text(ax, fitter, rect, lab, t,
                                  fs=bar.get("fs", t.fs_small), zorder=7)
                cc.add_text(tt, lab.replace("\n", " "), owner=key, fitted=ok)

        for mi, ms in enumerate(row.get("milestones", []) or []):
            x = xof(ms["at"])
            shapes.diamond(ax, x, cy, (px1 - px0) / n * 0.035, rowh * 0.20,
                           fill=t.outline, edge=t.outline, zorder=8)
            if ms.get("label"):
                tt = ax.text(x + (px1 - px0) / n * 0.06, cy, ms["label"],
                             ha="left", va="center", fontsize=t.fs_small,
                             color=t.text, zorder=8)
                cc.add_text(tt, ms["label"], owner=None)
