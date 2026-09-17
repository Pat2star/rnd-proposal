# -*- coding: utf-8 -*-
"""선언적 스펙 → 사이클 개괄도 PNG/PDF.

    PYTHONPATH=$CLAUDE_PLUGIN_ROOT python -m engine.figure.schematic --spec specs/hp_cascade_fig1.yaml \\
        --out fig1.png --assert-no-overlap

스펙 예시는 specs/ 참조. 그림 1장당 18KB 파이썬을 쓰던 것을 ~60줄 YAML로 바꾼다.
"""
from __future__ import annotations

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import yaml                              # noqa: E402

from . import glyphs, routing, textfit, theme as theme_mod   # noqa: E402

CANVAS = {
    "wide": (1600, 900), "band": (1600, 640),
    "hero": (1600, 1000), "tall": (1200, 1500),
}


def _setup_font(t):
    """한글 라벨을 위해 폰트를 잡는다. 없으면 조용히 폴백."""
    from matplotlib import font_manager as fm
    have = {f.name for f in fm.fontManager.ttflist}
    order = [t.font, "Malgun Gothic", "Noto Sans KR", t.font_en,
             "Times New Roman", "DejaVu Sans"]
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [f for f in order if f in have] or ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def _resolve(anchors, ref: str):
    """'comp.out' → 좌표. 'comp' 만 주면 center."""
    if isinstance(ref, (list, tuple)):
        return tuple(ref)
    parts = str(ref).split(".")
    a = anchors[parts[0]]
    return a[parts[1]] if len(parts) > 1 else a["center"]


def render_panel(ax, panel: dict, t, cc: textfit.CollisionChecker):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.axis("off")

    anchors: dict[str, dict] = {}

    # 1) 부품
    for c in panel.get("components", []):
        kind = c["type"]
        fn = glyphs.GLYPHS.get(kind)
        if fn is None:
            raise ValueError(f"알 수 없는 부품 타입 '{kind}'. "
                             f"가능: {sorted(glyphs.GLYPHS)}")
        x, y = c["at"]
        if kind in ("motor", "generator"):
            a = fn(ax, x, y, c.get("r", 0.026), c.get("label", "M"), theme=t)
        elif kind == "valve":
            a = fn(ax, x, y, c.get("size", 0.07), c.get("label", ""), theme=t)
        else:
            a = fn(ax, x, y, c.get("w", 0.14), c.get("h", 0.13),
                   c.get("label", ""), theme=t)
        anchors[c["id"]] = a

    # 2) 축 (부품 위에 겹치지 않게 배관보다 아래)
    for s in panel.get("shafts", []):
        glyphs.shaft(ax, anchors[s["from"]], anchors[s["to"]], theme=t)

    # 3) 배관
    for s in panel.get("streams", []):
        if "from" in s and "to" in s:
            routing.pipe(ax, _resolve(anchors, s["from"]),
                         _resolve(anchors, s["to"]), t,
                         fluid=s.get("fluid", "primary"),
                         mode=s.get("route", "auto"), detour=s.get("detour"))
        else:                                   # 열원/열침 스텁
            tgt = _resolve(anchors, s["to"])
            direction = s.get("direction", "up")
            # 스텁이 붙은 쪽을 기록해 두면 라벨을 반대쪽으로 보낼 수 있다
            cid = str(s["to"]).split(".")[0]
            if cid in anchors:
                anchors[cid].setdefault("stub_sides", set()).add(direction)
            routing.heat_stub(
                ax, tgt, t, fluid=s.get("fluid", "heat_sink"),
                direction=direction,
                length=s.get("length", 0.10), label=s.get("label"),
                label_side=s.get("label_side", "left"),
                dx=s.get("dx", 0.0), into=bool(s.get("into", False)))
            if s.get("label"):
                cc.texts.append(textfit.Placed(ax.texts[-1], "stream"))

    # 4) 부품 라벨 — 도형 안에 넣되 넘치면 축소/이동
    #    HX/밸브는 도형 밖에 두고, **열 스텁이 붙은 반대쪽**으로 자동 배치한다.
    for c in panel.get("components", []):
        a = anchors[c["id"]]
        lab = c.get("label")
        if not lab or a.get("kind") == "motor":
            continue
        if a["kind"] in ("hx", "valve"):
            pos = c.get("label_pos")
            if not pos:
                stubs = a.get("stub_sides") or set()
                pos = "above" if "down" in stubs and "up" not in stubs else \
                      ("below" if "up" in stubs else "below")
            tt = textfit.label_outside(ax, a, lab, t, pos)
        else:
            tt, _ = textfit.fit_inside(ax, *a["center"], lab, a["bbox"], t)
        cc.track(tt, c["id"])

    if panel.get("title"):
        tt = ax.set_title(panel["title"], fontsize=t.fs_panel,
                          fontweight="bold", loc="left", pad=8, color=t.text)
        cc.track(tt, "panel_title")


def render(spec: dict, out: str, assert_no_overlap: bool = False) -> dict:
    t = theme_mod.get(spec.get("preset", "turbo"))
    _setup_font(t)

    panels = spec.get("panels", [])
    grid = spec.get("grid") or ([2, 2] if len(panels) > 2 else [1, len(panels)])
    nr, nc = int(grid[0]), int(grid[1])
    cw, ch = CANVAS.get(spec.get("canvas", "wide"), CANVAS["wide"])
    dpi = int(spec.get("dpi", 200))

    # ★ 그림을 **인쇄 크기**로 저작한다 (실측 결함, 2026-08-18).
    #   전에는 fig_w를 16인치로 잡고 문서에서 170mm로 줄였다. 그러면 11pt 라벨이
    #   종이 위에서 11 x 6.69/16 = 4.6pt가 되어 읽히지 않는다.
    #   폭을 본문폭에 맞추면 pt 단위인 글자·선굵기·화살촉이 전부 실제 크기로 나온다.
    #   픽셀 해상도는 dpi를 역산해 기존과 동일하게 유지한다.
    width_mm = float(spec.get("width_mm", 170))          # 본문폭 48188 HWPUNIT ≈ 170mm
    target_px_w = cw * dpi / 100.0                        # 기존 동작과 같은 픽셀 폭
    fig_w = width_mm / 25.4
    # ★ 세로비는 캔버스가 정한다. 전에는 (nr/nc)를 곱해서 정사각 그리드가 아니면
    #   선언한 캔버스 AR과 어긋났다(grid [1,3]은 게이트 3.6에서 반드시 FAIL).
    fig_h = fig_w * ch / cw
    dpi = target_px_w / fig_w
    # 패널이 여러 개면 패널 하나가 그만큼 좁아지므로 글자·선도 같이 줄인다.
    # 안 줄이면 4패널에서 라벨이 겹친다(실측: 'Heat source' ↔ 'Comp_b' 3건).
    #   단일 패널은 본문폭을 통째로 쓰므로 명목 크기 그대로 쓴다.
    #   여러 패널이면 패널 하나가 좁아지므로 열 수에 반비례로 줄이고, 밀집한
    #   도면에 여백을 주기 위해 20%를 더 뺀다. 이 값은 --assert-no-overlap 이
    #   지킨다 (실측: 4패널에서 1.0/nc면 Comp_b 라벨이 도형 밖으로 밀려난다).
    fs_scale = 1.0 if nc <= 1 else 0.80 / nc
    if fs_scale < 0.999:
        import dataclasses
        t = dataclasses.replace(
            t,
            fs_glyph=t.fs_glyph * fs_scale, fs_glyph_small=t.fs_glyph_small * fs_scale,
            fs_stream=t.fs_stream * fs_scale, fs_caption=t.fs_caption * fs_scale,
            fs_panel=t.fs_panel * fs_scale,
            lw_component=t.lw_component * fs_scale, lw_zigzag=t.lw_zigzag * fs_scale,
            lw_stream=t.lw_stream * fs_scale, lw_thin=t.lw_thin * fs_scale)

    fig, axes = plt.subplots(nr, nc, figsize=(fig_w, fig_h))
    fig.patch.set_facecolor(t.surface)
    axs = [axes] if nr * nc == 1 else list(axes.flat)

    cc = textfit.CollisionChecker(axs[0])
    hits_all = []
    for i, ax in enumerate(axs):
        if i < len(panels):
            c = textfit.CollisionChecker(ax)
            render_panel(ax, panels[i], t, c)
            hits_all += [f"패널{i+1}: {h}" for h in c.check()]
        else:
            ax.axis("off")

    # 캡션은 그림에 넣지 않는다 — HWPX가 hp:autoNum으로 붙이므로 이중이 된다.
    # 범례만 짧게 허용한다.
    legend = spec.get("legend") or spec.get("caption")
    if legend:
        fig.text(0.5, 0.012, legend, ha="center", va="bottom",
                 fontsize=t.fs_caption, color=t.text)

    fig.subplots_adjust(left=0.02, right=0.98, top=0.94,
                        bottom=0.07 if (spec.get("legend") or spec.get("caption")) else 0.03,
                        wspace=0.10, hspace=0.22)

    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    fig.savefig(out, dpi=dpi, facecolor=t.surface)
    root, _ = os.path.splitext(out)
    fig.savefig(root + ".pdf", facecolor=t.surface)
    plt.close(fig)

    from PIL import Image
    with Image.open(out) as im:
        px = im.size
    return {"out": out, "px": px, "aspect": px[0] / px[1],
            "overlaps": hits_all, "panels": len(panels)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--assert-no-overlap", action="store_true")
    a = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(a.spec, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    r = render(spec, a.out, a.assert_no_overlap)
    print(f"개괄도 생성 → {r['out']}  {r['px'][0]}x{r['px'][1]} "
          f"(AR {r['aspect']:.3f}), 패널 {r['panels']}")
    if r["overlaps"]:
        print(f"  라벨 충돌 {len(r['overlaps'])}건:")
        for h in r["overlaps"]:
            print(f"    - {h}")
        if a.assert_no_overlap:
            return 2
    else:
        print("  라벨 충돌 0건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
