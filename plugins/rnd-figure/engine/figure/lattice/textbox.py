# -*- coding: utf-8 -*-
"""격자 안에 글자를 넣고 **넘쳤는지 기계로 확인한다**.

## 왜 별도로 짰나

`schematic/textfit.py` 는 「도형 안에 안 들어가면 도형 **밖 아래**로 내보낸다」.
개괄도에서는 그게 옳다 — 배관 사이 여백이 넉넉하다.
격자에서는 **밖이 곧 옆 칸**이다. 내보내면 이웃 라벨을 덮는다.
그래서 여기서는 밖으로 내보내지 않고 **줄바꿈 → 축소 → 그래도 안 되면 적발**한다.

## 무엇을 적발하나 (세 가지, 전부 실제 bbox 측정)

1. **글자 ↔ 글자** 교차
2. **넘침** — 글자가 자기 칸(owner box)을 벗어남
3. **침범** — 글자가 남의 칸(foreign box)을 파고듦
4. **도판 이탈** — 글자가 그림 경계(0~1) 밖으로 나감

전례: `generation_report.md` 가 "All component labels rendered correctly" PASS 를
선언했는데 실제 겹침이 8건 이상이었다. matplotlib 이 stderr 를 안 냈다는 뜻일 뿐이다.
그래서 여기서는 **판정이 exit code 로 나간다.**

## 상자 등록 규칙 — 잎(leaf)만 등록한다

칸 안에 칸을 등록하면 안쪽 글자가 바깥 칸을 「침범」한 것으로 잡혀 거짓 적발이 된다.
글자를 직접 소유하는 **가장 안쪽 상자만** `add_box` 한다.
(위험도 매트릭스의 셀은 등록하지 않고 그 안의 칩만 등록한다.)
"""
from __future__ import annotations

from dataclasses import dataclass

# 줄바꿈 허용 지점 — 공백 뒤, 그리고 이 문자들 뒤
BREAK_AFTER = " ·/,、"


@dataclass
class Placed:
    artist: object
    name: str
    owner: str | None


def renderer(fig):
    try:
        return fig.canvas.get_renderer()
    except AttributeError:                       # pragma: no cover - 백엔드 의존
        fig.canvas.draw()
        return fig.canvas.get_renderer()


def bbox_data(ax, artist):
    """아티스트의 data 좌표 bbox (x0, y0, x1, y1)."""
    bb = artist.get_window_extent(renderer=renderer(ax.figure))
    inv = ax.transData.inverted()
    (x0, y0), (x1, y1) = inv.transform(bb.get_points())
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def overlap(a, b, tol=0.0):
    """두 bbox 가 tol 이상 파고들면 True."""
    return not (a[2] <= b[0] + tol or b[2] <= a[0] + tol
                or a[3] <= b[1] + tol or b[3] <= a[1] + tol)


def contains(outer, inner, tol=0.0):
    return (inner[0] >= outer[0] - tol and inner[2] <= outer[2] + tol
            and inner[1] >= outer[1] - tol and inner[3] <= outer[3] + tol)


def _tokens(s: str) -> list[str]:
    out, cur = [], ""
    for ch in s:
        cur += ch
        if ch in BREAK_AFTER:
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


class Fitter:
    """측정기 — 텍스트 크기를 실제로 재서 줄바꿈·축소를 결정한다."""

    def __init__(self, ax):
        self.ax = ax
        self._cache: dict = {}

    def size(self, s: str, fs: float, weight="normal") -> tuple[float, float]:
        key = (s, round(fs, 2), weight)
        if key in self._cache:
            return self._cache[key]
        t = self.ax.text(0, 0, s, fontsize=fs, fontweight=weight,
                         ha="left", va="bottom")
        b = bbox_data(self.ax, t)
        t.remove()
        v = (b[2] - b[0], b[3] - b[1])
        self._cache[key] = v
        return v

    def wrap(self, text: str, fs: float, maxw: float, weight="normal") -> str:
        """maxw 안에 들어가도록 줄바꿈. 스펙에 쓴 \n 은 존중한다."""
        out_lines = []
        for para in str(text).split("\n"):
            cur = ""
            for tk in _tokens(para):
                trial = (cur + tk) if cur else tk.lstrip()
                if not trial.strip():
                    continue
                if self.size(trial.rstrip(), fs, weight)[0] <= maxw or not cur:
                    cur = trial
                else:
                    out_lines.append(cur.rstrip())
                    cur = tk.lstrip()
            # 토큰 하나가 통째로 폭을 넘으면 글자 단위로 쪼갠다
            if cur and self.size(cur.rstrip(), fs, weight)[0] > maxw:
                buf = ""
                for ch in cur.rstrip():
                    if buf and self.size(buf + ch, fs, weight)[0] > maxw:
                        out_lines.append(buf)
                        buf = ch
                    else:
                        buf += ch
                cur = buf
            if cur.strip():
                out_lines.append(cur.rstrip())
        return "\n".join(out_lines) or " "


def fit_text(ax, fitter: Fitter, box, text, theme, fs=None, fs_min=None,
             weight="normal", color=None, pad=(0.90, 0.86), zorder=6,
             align="center"):
    """상자 안에 글자를 넣는다. 줄바꿈 → 축소 순. 밖으로 내보내지 않는다.

    box   = (x0, y0, x1, y1)  data 좌표
    pad   = (가로 사용률, 세로 사용률)
    반환  = (Text, fitted: bool)  — fitted=False 면 넘친 것이다(적발 대상).
    """
    x0, y0, x1, y1 = box
    bw, bh = (x1 - x0) * pad[0], (y1 - y0) * pad[1]
    fs = fs or theme.fs_node
    fs_min = fs_min if fs_min is not None else theme.fs_min
    # fs_min 은 **가독 하한**이다. 명목 크기가 하한보다 작으면 하한을 쓴다.
    # (이 분기가 없으면 while 이 한 번도 안 돌아 best 가 None 으로 남는다 —
    #  test_detects_text_overflow 가 잡아낸 실제 결함이다.)
    fs = max(float(fs), float(fs_min))
    color = color or theme.text

    best = None
    cur = fs
    while cur >= fs_min - 1e-9:
        s = fitter.wrap(text, cur, bw, weight)
        w, h = fitter.size(s, cur, weight)
        if best is None:
            best = (s, cur)
        if w <= bw and h <= bh:
            best = (s, cur)
            break
        best = (s, cur)
        cur -= 0.5
    s, cur = best
    w, h = fitter.size(s, cur, weight)
    fitted = (w <= bw and h <= bh)

    if align == "left":
        tx, ha = x0 + (x1 - x0) * (1 - pad[0]) / 2, "left"
    elif align == "right":
        tx, ha = x1 - (x1 - x0) * (1 - pad[0]) / 2, "right"
    else:
        tx, ha = (x0 + x1) / 2, "center"
    t = ax.text(tx, (y0 + y1) / 2, s, ha=ha, va="center", fontsize=cur,
                fontweight=weight, color=color, zorder=zorder,
                linespacing=1.25)
    return t, fitted


class Checker:
    """렌더 후 전수 검사. 통과가 아니라 **적발**을 목적으로 한다."""

    # 허용 침투량 (data 좌표). 폰트 렌더러의 안티에일리어싱 여유만 흡수한다.
    TOL = 0.0015

    def __init__(self, ax):
        self.ax = ax
        self.texts: list[Placed] = []
        self.boxes: dict[str, tuple] = {}
        self.overflow: list[str] = []

    def add_box(self, key: str, box):
        """잎 상자만 등록한다 (docstring 상단 규칙 참조)."""
        self.boxes[key] = tuple(box)

    def add_text(self, artist, name: str, owner: str | None = None,
                 fitted: bool = True):
        self.texts.append(Placed(artist, name, owner))
        if not fitted:
            self.overflow.append(f"'{name}' 이(가) 최소 글자크기에서도 칸에 안 들어감")
        return artist

    def check(self) -> list[str]:
        hits = list(self.overflow)
        measured = []
        for p in self.texts:
            try:
                measured.append((bbox_data(self.ax, p.artist), p))
            except Exception:                        # noqa: BLE001
                continue

        # 1) 글자 ↔ 글자
        for i in range(len(measured)):
            for j in range(i + 1, len(measured)):
                if overlap(measured[i][0], measured[j][0], self.TOL):
                    hits.append(f"글자 겹침 '{measured[i][1].name}' ↔ "
                                f"'{measured[j][1].name}'")

        # 2) 넘침 + 3) 침범 + 4) 도판 이탈
        for bb, p in measured:
            if not contains((0.0, 0.0, 1.0, 1.0), bb, self.TOL):
                hits.append(f"도판 이탈 '{p.name}' 이(가) 그림 경계를 벗어남")
            if p.owner and p.owner in self.boxes:
                if not contains(self.boxes[p.owner], bb, self.TOL):
                    hits.append(f"칸 넘침 '{p.name}' 이(가) '{p.owner}' 밖으로 나감")
            for key, box in self.boxes.items():
                if key == p.owner:
                    continue
                if overlap(box, bb, self.TOL):
                    hits.append(f"칸 침범 '{p.name}' 이(가) '{key}' 칸을 파고듦")
        # 같은 사고가 두 규칙에 걸릴 수 있으므로 중복을 없앤다
        seen, uniq = set(), []
        for h in hits:
            if h not in seen:
                seen.add(h)
                uniq.append(h)
        return uniq
