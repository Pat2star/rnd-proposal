# -*- coding: utf-8 -*-
"""선언적 스펙 → 격자형 그림 PNG/PDF (조직도 · 진도표 · 위험도 매트릭스).

    PYTHONPATH=$CLAUDE_PLUGIN_ROOT python -m engine.figure.lattice --spec specs/hthp_org_fig5.yaml \
        --out fig05.png --assert-no-overlap

## 왜 개괄도 엔진과 갈라 놓았나

`CLAUDE.md` 절대원칙 7 은 그림을 둘로 나눈다 — 사이클은 개괄도 엔진, 그 외는 Gemini.
그런데 **조직도·진도표·위험도 매트릭스는 둘 다 아니다.**

  · 사이클이 아니다 → 개괄도의 글리프 어휘(압축기·열교환기·밸브·축) 밖이다
  · **라벨이 곧 내용**이다 → AI 이미지는 한글 라벨을 정확히 못 넣는다.
    「글자 없이 그리고 캡션이 의미를 진다」는 경로 B 규칙 자체가 성립하지 않는다.

이 공백 때문에 hthp-2027 의 위험도 매트릭스·실증 마일스톤 그림을 만들지 못하고
철회한 전례가 있다(`workspace/hthp-2027/research/00_개정지시_R2.md` §2-7).

## 개괄도 엔진과 같이 지키는 것

  · 스펙은 YAML 하나다. 그림마다 파이썬을 새로 짜지 않는다.
  · **인쇄 폭(width_mm)으로 저작**하고 해상도는 dpi 로만 올린다.
    16in 로 그려 170mm 로 줄이면 11pt 라벨이 종이에서 4.6pt 가 된다(실측 사고).
  · 배경은 흰색이다. 게이트 3.9 가 네 모서리를 검사한다.
  · `--assert-no-overlap` 이 exit 2 로 나간다. 「이상 없음」 문장을 믿지 않는다.
"""
from __future__ import annotations

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import yaml                              # noqa: E402

from . import gantt, orgchart, riskmatrix   # noqa: E402
from . import theme as theme_mod            # noqa: E402
from .textbox import Checker, Fitter        # noqa: E402

KINDS = {
    "orgchart": orgchart.render,
    "gantt": gantt.render,
    "riskmatrix": riskmatrix.render,
}


def _setup_font(t):
    """한글 라벨용 폰트. 없으면 조용히 폴백한다."""
    from matplotlib import font_manager as fm
    have = {f.name for f in fm.fontManager.ttflist}
    order = [t.font, "Malgun Gothic", "Noto Sans KR", t.font_en,
             "Times New Roman", "DejaVu Sans"]
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [f for f in order if f in have] or ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def render(spec: dict, out: str) -> dict:
    kind = spec.get("kind")
    fn = KINDS.get(kind)
    if fn is None:
        raise ValueError(f"알 수 없는 격자 종류 '{kind}'. 가능: {sorted(KINDS)}")

    t = theme_mod.get(spec.get("preset", "turbo"))
    if spec.get("fs_min") is not None:
        import dataclasses
        t = dataclasses.replace(t, fs_min=float(spec["fs_min"]))
    _setup_font(t)

    cw, ch = theme_mod.CANVAS.get(spec.get("canvas", "wide"),
                                  theme_mod.CANVAS["wide"])
    dpi_nom = int(spec.get("dpi", 200))

    # ★ 인쇄 크기로 저작한다 (schematic/__main__.py 와 같은 계산).
    #   pt 단위인 글자·선굵기가 종이 위에서 선언한 값 그대로 나온다.
    width_mm = float(spec.get("width_mm", 170))
    fig_w = width_mm / 25.4
    fig_h = fig_w * ch / cw
    dpi = (cw * dpi_nom / 100.0) / fig_w

    fig = plt.figure(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor(t.surface)
    # 축은 캔버스를 통째로 쓴다. 여백은 스펙의 area 가 정한다 — 두 군데서
    # 여백을 주면 어느 쪽이 먹었는지 알 수 없게 된다.
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(t.surface)

    legend = spec.get("legend")
    if legend:
        fig.text(0.5, 0.012, legend, ha="center", va="bottom",
                 fontsize=t.fs_small, color=t.text)

    cc = Checker(ax)
    fitter = Fitter(ax)
    fn(ax, spec, t, cc, fitter)
    hits = cc.check()

    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    fig.savefig(out, dpi=dpi, facecolor=t.surface)
    root, _ = os.path.splitext(out)
    fig.savefig(root + ".pdf", facecolor=t.surface)
    plt.close(fig)

    from PIL import Image
    with Image.open(out) as im:
        px = im.size
    return {"out": out, "kind": kind, "px": px, "aspect": px[0] / px[1],
            "overlaps": hits}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--assert-no-overlap", action="store_true")
    a = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                # noqa: BLE001
        pass
    with open(a.spec, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    r = render(spec, a.out)
    print(f"격자도({r['kind']}) 생성 → {r['out']}  {r['px'][0]}x{r['px'][1]} "
          f"(AR {r['aspect']:.3f})")
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
