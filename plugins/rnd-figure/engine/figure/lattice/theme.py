# -*- coding: utf-8 -*-
"""격자형 그림 프리셋 — 조직도 · 진도표 · 위험도 매트릭스.

사이클 개괄도(`engine.figure.schematic`)와 **같은 팔레트**를 쓴다.
한 문서 안에서 그림이 한 벌로 보여야 하기 때문이다.

시각 문법 (사용자 소유 — `CLAUDE.md` 「사람이 소유하는 것」)
  · 장식용 그룹박스를 두르지 않는다. 상자는 **정보 단위**일 때만 그린다.
  · 색은 역할 구분에만 쓴다. 강조를 위해 색을 더하지 않는다.
  · 격자선은 얇은 회색 한 종류다. 굵기·색을 섞지 않는다.

★ 격자형에서 「수치 금지」는 적용되지 않는다.
  개괄도의 금지 대상은 **운전 조건 수치**(온도·압력·유량)다.
  진도표의 연도·TRL, 매트릭스의 축 눈금은 **그림의 내용 자체**이며
  캡션으로 옮길 수 없다. 옮기면 격자가 빈 껍데기가 된다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 표준 캔버스 — engine.quality.gate 의 CAN 과 반드시 같아야 한다.
# 어긋나면 게이트 3.6(AR 일치)이 반드시 FAIL 한다. tests 가 1:1로 묶어 둔다.
CANVAS = {
    "wide": (1600, 900),      # 16:9
    "band": (1600, 640),      # 2.5:1
    "hero": (1600, 1000),     # 1.6:1
    "tall": (1200, 1500),     # 0.8
}


@dataclass
class LatticeTheme:
    name: str
    # 색
    outline: str = "#1A1A1A"
    surface: str = "#FFFFFF"
    text: str = "#000000"
    grid: str = "#9AA0A6"
    edge: str = "#1A1A1A"
    # 선 굵기 (pt — 인쇄 폭으로 저작하므로 실제 pt 그대로 나온다)
    lw_box: float = 1.3
    lw_box_strong: float = 1.9
    lw_grid: float = 0.7
    lw_edge: float = 1.1
    # 글자 (pt)
    fs_node: float = 10.0
    fs_row: float = 9.5
    fs_head: float = 10.0
    fs_small: float = 8.5
    fs_title: float = 11.5
    fs_min: float = 7.0        # 가독 하한. schematic 의 min_fontsize 와 같다
    font: str = "Malgun Gothic"
    font_en: str = "Times New Roman"
    # 역할별 상자 서식 — 조직도
    roles: dict = field(default_factory=lambda: {
        "lead":    {"fill": "#FBEBC0", "edge": "#1A1A1A", "ls": "solid",  "strong": True},
        "joint":   {"fill": "#FFFFFF", "edge": "#1A1A1A", "ls": "solid",  "strong": False},
        "entrust": {"fill": "#F1F3F5", "edge": "#1A1A1A", "ls": "solid",  "strong": False},
        "partner": {"fill": "#FFFFFF", "edge": "#5A5A5A", "ls": "dashed", "strong": False},
        "group":   {"fill": "#E7EDF5", "edge": "#1A1A1A", "ls": "solid",  "strong": False},
        "plain":   {"fill": "#FFFFFF", "edge": "#1A1A1A", "ls": "solid",  "strong": False},
    })
    # 막대 서식 — 진도표
    bars: dict = field(default_factory=lambda: {
        "phase1": {"fill": "#BCD0EA", "edge": "#1A1A1A", "hatch": None},
        "phase2": {"fill": "#F5C7AB", "edge": "#1A1A1A", "hatch": None},
        "prep":   {"fill": "#FFFFFF", "edge": "#5A5A5A", "hatch": "///"},
        "plain":  {"fill": "#E9ECEF", "edge": "#1A1A1A", "hatch": None},
    })
    # 위험 등급 음영 — 무채색 램프. 신호등 색을 쓰지 않는다(논문 톤).
    zones: list = field(default_factory=lambda: [
        "#FFFFFF", "#F5F6F7", "#EBEDEF", "#DFE2E6", "#D2D6DB",
    ])


TURBO = LatticeTheme(name="turbo")

# 무채색 판 — Methanol 계열 논문 톤 (schematic 의 pfd 와 짝)
PFD = LatticeTheme(
    name="pfd",
    grid="#9A9A9A",
    roles={
        "lead":    {"fill": "#DCDFE3", "edge": "#1A1A1A", "ls": "solid",  "strong": True},
        "joint":   {"fill": "#FFFFFF", "edge": "#1A1A1A", "ls": "solid",  "strong": False},
        "entrust": {"fill": "#F1F3F5", "edge": "#1A1A1A", "ls": "solid",  "strong": False},
        "partner": {"fill": "#FFFFFF", "edge": "#5A5A5A", "ls": "dashed", "strong": False},
        "group":   {"fill": "#EBEDEF", "edge": "#1A1A1A", "ls": "solid",  "strong": False},
        "plain":   {"fill": "#FFFFFF", "edge": "#1A1A1A", "ls": "solid",  "strong": False},
    },
    bars={
        "phase1": {"fill": "#D5D9DE", "edge": "#1A1A1A", "hatch": None},
        "phase2": {"fill": "#AEB4BB", "edge": "#1A1A1A", "hatch": None},
        "prep":   {"fill": "#FFFFFF", "edge": "#5A5A5A", "hatch": "///"},
        "plain":  {"fill": "#E9ECEF", "edge": "#1A1A1A", "hatch": None},
    },
)

PRESETS = {"turbo": TURBO, "pfd": PFD}


def get(name: str) -> LatticeTheme:
    if name not in PRESETS:
        raise ValueError(f"알 수 없는 프리셋 '{name}'. 가능: {list(PRESETS)}")
    return PRESETS[name]
