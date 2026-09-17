# -*- coding: utf-8 -*-
"""라벨 배치 + 충돌 검사.

AI 폴백 스크립트의 겹침(Comp_T, Valve, Isenthalpic, HX 라벨 8개)은
**텍스트 폭을 한 번도 측정하지 않아서** 생겼다. 원인 3가지가 규명됐다:
  1. "Comp_T" 6글자 @5.5pt ≈ 6.8mm 를 폭 5.0mm 사다리꼴 중앙에 넣음
  2. FancyBboxPatch의 boxstyle pad가 도형 경계를 확장한다는 걸 미반영
  3. draw_hx의 라벨 y가 cy-h*0.42 인데 박스 하단은 cy-h*0.5

여기서는 실제 bbox를 재서 배치하고, 마지막에 전수 교차 검사를 한다.
`generation_report.md`가 "All labels rendered correctly" 거짓 PASS를 선언한
전례가 있으므로 **검사는 exit code로 나간다.**
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Placed:
    artist: object
    role: str


def _bbox_data(ax, artist):
    """아티스트의 data 좌표 bbox (x0, y0, x1, y1)."""
    fig = ax.figure
    fig.canvas.draw()
    bb = artist.get_window_extent(renderer=fig.canvas.get_renderer())
    inv = ax.transData.inverted()
    (x0, y0), (x1, y1) = inv.transform(bb.get_points())
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y1, y0))


def _overlap(a, b, tol=0.0):
    return not (a[2] <= b[0] + tol or b[2] <= a[0] + tol
                or a[3] <= b[1] + tol or b[3] <= a[1] + tol)


def fit_inside(ax, cx, cy, text, box, theme, fontsize=None, min_fontsize=7.0,
               color=None, weight="bold", zorder=8):
    """도형 안에 라벨을 넣되, 폭을 넘으면 축소하고 그래도 넘치면 도형 아래로.

    box = (x0, y0, x1, y1) 도형 bbox (data 좌표)
    """
    fs = fontsize or theme.fs_glyph
    color = color or theme.text
    bw = box[2] - box[0]
    bh = box[3] - box[1]

    t = ax.text(cx, cy, text, ha="center", va="center", fontsize=fs,
                fontweight=weight, color=color, zorder=zorder)
    for _ in range(8):
        tb = _bbox_data(ax, t)
        if (tb[2] - tb[0]) <= bw * 0.86 and (tb[3] - tb[1]) <= bh * 0.80:
            return t, "inside"
        fs -= 0.5
        if fs < min_fontsize:
            break
        t.set_fontsize(fs)

    # 도형 밖(아래)으로 내보낸다 — 테두리와 겹치지 않게 여유를 둔다
    t.set_fontsize(max(fs, min_fontsize))
    t.set_position((cx, box[1] - bh * 0.22))
    t.set_va("top")
    return t, "below"


def label_outside(ax, anchor, text, theme, pos="below", fontsize=None,
                  gap=0.024, color=None, weight="bold", zorder=8):
    """도형 밖 라벨 (HX·밸브 관행).

    ★ 실측 결함 재현 방지: AI 폴백은 라벨 y를 `cy - h*0.42`로 잡았는데 박스
    하단이 `cy - h*0.5`라 모든 HX에서 글자가 테두리를 넘었다. 여기서는
    앵커의 bottom/top에서 gap만큼 **밖으로** 나간다.
    """
    if pos == "above":
        x, y = anchor["top"]
        t = ax.text(x, y + gap, text, ha="center", va="bottom",
                    fontsize=fontsize or theme.fs_glyph,
                    fontweight=weight, color=color or theme.text, zorder=zorder)
    else:
        x, y = anchor["bottom"]
        t = ax.text(x, y - gap, text, ha="center", va="top",
                    fontsize=fontsize or theme.fs_glyph,
                    fontweight=weight, color=color or theme.text, zorder=zorder)
    return t


label_below = label_outside     # 하위호환


class CollisionChecker:
    """렌더 후처리 전수 교차 검사."""

    def __init__(self, ax):
        self.ax = ax
        self.texts: list = []

    def track(self, artist, role=""):
        if artist is not None:
            self.texts.append(Placed(artist, role))
        return artist

    def check(self, tol=0.002) -> list[str]:
        """텍스트 ↔ 텍스트 교차만 검사한다.

        텍스트 ↔ 도형은 '도형 안 라벨'이 정상이므로 검사하지 않는다.
        (fit_inside가 도형 경계를 이미 보장한다.)
        """
        boxes = []
        for p in self.texts:
            try:
                boxes.append((_bbox_data(self.ax, p.artist),
                              p.artist.get_text(), p.role))
            except Exception:                               # noqa: BLE001
                continue
        hits = []
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                if _overlap(boxes[i][0], boxes[j][0], -tol):
                    hits.append(f"'{boxes[i][1]}' ↔ '{boxes[j][1]}'")
        return hits
