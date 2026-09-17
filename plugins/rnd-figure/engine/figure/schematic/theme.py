# -*- coding: utf-8 -*-
"""개괄도 프리셋 — turbo (GT2026/HP cascade 계열) / pfd (Methanol 계열).

실측 근거: 사용자 본인 논문 3편의 공통 철학
  · 도면에 수치를 넣지 않는다 (조건은 표·캡션으로 분리)
  · 상태점 번호를 쓰지 않는다
  · 열교환기는 원+물결 또는 사각+지그재그
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Theme:
    name: str
    # 색
    outline: str = "#1A1A1A"
    surface: str = "#FFFFFF"
    cool: str = "#5B8FD4"          # 압축기 입구 / 팽창기 출구
    hot: str = "#E8783C"           # 압축기 출구 / 팽창기 입구
    hx_fill: str = "#FBEBC0"
    valve_fill: str = "#B8BCC4"
    shaft_fill: str = "#D3D3D3"
    text: str = "#000000"
    # 선
    lw_component: float = 1.6
    lw_zigzag: float = 1.4
    lw_stream: float = 1.6
    lw_thin: float = 0.8
    shaft_thickness: float = 0.030
    # 글자
    font: str = "Malgun Gothic"
    font_en: str = "Times New Roman"
    fs_glyph: float = 11.0
    fs_glyph_small: float = 8.0
    fs_stream: float = 9.0
    fs_panel: float = 12.0
    fs_caption: float = 10.0
    # 유체 클래스
    fluids: dict = field(default_factory=lambda: {
        "primary":     {"color": "#1A1A1A", "style": "solid"},
        "secondary":   {"color": "#00B050", "style": "solid"},
        "heat_sink":   {"color": "#2E75D4", "style": "dashed"},
        "heat_source": {"color": "#E02020", "style": "dashed"},
    })


TURBO = Theme(name="turbo")

PFD = Theme(
    name="pfd",
    outline="#1A1A1A", surface="#FFFFFF",
    cool="#C8CDD4", hot="#9AA2AC",          # 무채색 — Methanol 논문 톤
    hx_fill="#E8EAEC", valve_fill="#C8CDD4", shaft_fill="#D3D3D3",
    lw_component=1.4, lw_zigzag=1.2,
    fluids={
        "primary":     {"color": "#1A1A1A", "style": "solid"},
        "secondary":   {"color": "#5A5A5A", "style": "solid"},
        "heat_sink":   {"color": "#1A1A1A", "style": "dashed"},
        "heat_source": {"color": "#1A1A1A", "style": "dashed"},
    },
)

PRESETS = {"turbo": TURBO, "pfd": PFD}


def get(name: str) -> Theme:
    if name not in PRESETS:
        raise ValueError(f"알 수 없는 프리셋 '{name}'. 가능: {list(PRESETS)}")
    return PRESETS[name]
