# -*- coding: utf-8 -*-
"""header.xml 인덱서 — 서식 정의를 id로 조회 가능한 형태로 만든다.

이 모듈은 header.xml을 **읽기만** 한다. ZIP 복제 방식에서 header.xml은
바이트 단위로 보존되므로 여기서 얻은 id는 그대로 section0.xml에 쓸 수 있다.

함정 2가지 (docs/hwpx_format_notes.md §3, §4 참조):
  1. paraPr의 margin/lineSpacing은 직계 자식이 아니라 hp:switch/hp:case 안에 있다.
     43개 paraPr 전부가 switch를 갖는다. 직계만 찾으면 값을 전부 놓친다.
  2. borderFill은 1-base다 (1~25, 0번 없음). 0을 유효로 보면 검증기가 오탐한다.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field

from lxml import etree

from .consts import NS


# ── 저수준 헬퍼 ────────────────────────────────────────────────────
def _switch_source(el):
    """paraPr에서 실제 값이 든 서브트리를 고른다.

    hp:case (HwpUnitChar 네임스페이스 분기) 가 있으면 그쪽 값이 진짜다 —
    linesegarray의 horzpos가 case 값(1500/2500/5000)과 일치한다.
    hp:default 값은 정확히 case × 2 이므로 쓰면 들여쓰기가 두 배가 된다.
    """
    case = el.find(".//hp:switch/hp:case", NS)
    return case if case is not None else el


def _find_in(el, path):
    """hp:case 우선, 없으면 직계에서 찾는다."""
    src = _switch_source(el)
    found = src.find(path, NS)
    if found is None:
        found = el.find(path, NS)
    return found


def _val(el, path):
    found = _find_in(el, path)
    return int(found.get("value")) if found is not None else None


def _int_attr(el, name, default=None):
    if el is None or el.get(name) is None:
        return default
    try:
        return int(el.get(name))
    except ValueError:
        return default


# ── 레코드 ─────────────────────────────────────────────────────────
@dataclass
class ParaPr:
    id: str
    align: str | None = None
    line_spacing_pct: int | None = None
    line_spacing_type: str | None = None
    indent_left: int | None = None
    indent_right: int | None = None
    intent: int | None = None          # 내어쓰기 (음수)
    space_prev: int | None = None
    space_next: int | None = None
    heading_type: str = "NONE"         # NONE | BULLET | OUTLINE
    heading_id_ref: str | None = None
    heading_level: int | None = None
    tab_pr: str | None = None
    condense: int | None = None
    default_left: int | None = None    # hp:default 쪽 값 (검증용)


@dataclass
class CharPr:
    id: str
    height: int | None = None          # HWPUNIT = pt × 100
    text_color: str | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    ratio: int | None = None           # 장평
    spacing: int | None = None         # 자간
    font_hangul: str | None = None     # 인덱스 → 이름으로 해석된 값

    @property
    def is_colored(self) -> bool:
        """검정이 아닌 글자색 = 양식 작성 안내문/교정 표시일 가능성이 높다."""
        return bool(self.text_color) and self.text_color.upper() not in (
            "#000000", "NONE")


@dataclass
class BorderFill:
    id: str
    left: str | None = None
    right: str | None = None
    top: str | None = None
    bottom: str | None = None
    fill: str | None = None            # faceColor, 투명/흰색이면 None

    def spec(self) -> tuple:
        """(l, r, t, b, fill) — 역인덱스 키."""
        return (self.left, self.right, self.top, self.bottom, self.fill)


@dataclass
class Style:
    id: str
    name: str | None = None
    eng_name: str | None = None
    para_pr: str | None = None
    char_pr: str | None = None


@dataclass
class HeaderIndex:
    para_pr: dict[str, ParaPr] = field(default_factory=dict)
    char_pr: dict[str, CharPr] = field(default_factory=dict)
    border_fill: dict[str, BorderFill] = field(default_factory=dict)
    style: dict[str, Style] = field(default_factory=dict)
    bullets: dict[str, str] = field(default_factory=dict)          # id → char
    numberings: dict[str, list[str]] = field(default_factory=dict)  # id → level formats
    fonts_hangul: list[str] = field(default_factory=list)
    tab_pr_ids: list[str] = field(default_factory=list)
    item_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    # ── 조회 편의 ──
    def border_fill_index(self) -> dict[tuple, str]:
        """spec → id 역인덱스. 중복 spec은 가장 작은 id 우선."""
        idx: dict[tuple, str] = {}
        for bid in sorted(self.border_fill, key=int):
            idx.setdefault(self.border_fill[bid].spec(), bid)
        return idx

    def bullet_para_prs(self) -> dict[str, int]:
        """heading.type == BULLET 인 paraPr → indent_left."""
        return {pid: (p.indent_left or 0)
                for pid, p in self.para_pr.items()
                if p.heading_type == "BULLET"}

    def outline_para_prs(self) -> dict[str, int]:
        return {pid: (p.indent_left or 0)
                for pid, p in self.para_pr.items()
                if p.heading_type == "OUTLINE"}


# ── 파서 ───────────────────────────────────────────────────────────
def _parse_fonts(root) -> list[str]:
    """HANGUL 그룹 fontface의 폰트 이름 목록 (fontRef@hangul 인덱스용)."""
    for ff in root.iter("{%s}fontface" % NS['hh']):
        if ff.get("lang") == "HANGUL":
            return [f.get("face") for f in ff.findall("hh:font", NS)]
    return []


def _parse_para_pr(el) -> ParaPr:
    align = el.find("hh:align", NS)
    heading = el.find("hh:heading", NS)
    lsp = _find_in(el, "hh:lineSpacing")
    default_left = el.find(".//hp:switch/hp:default/hh:margin/hc:left", NS)

    return ParaPr(
        id=el.get("id"),
        align=align.get("horizontal") if align is not None else None,
        line_spacing_pct=_int_attr(lsp, "value"),
        line_spacing_type=lsp.get("type") if lsp is not None else None,
        indent_left=_val(el, "hh:margin/hc:left"),
        indent_right=_val(el, "hh:margin/hc:right"),
        intent=_val(el, "hh:margin/hc:intent"),
        space_prev=_val(el, "hh:margin/hc:prev"),
        space_next=_val(el, "hh:margin/hc:next"),
        heading_type=heading.get("type") if heading is not None else "NONE",
        heading_id_ref=heading.get("idRef") if heading is not None else None,
        heading_level=_int_attr(heading, "level"),
        tab_pr=el.get("tabPrIDRef"),
        condense=_int_attr(el, "condense"),
        default_left=_int_attr(default_left, "value"),
    )


def _parse_char_pr(el, fonts_hangul) -> CharPr:
    ref = el.find("hh:fontRef", NS)
    ratio = el.find("hh:ratio", NS)
    spacing = el.find("hh:spacing", NS)
    ul = el.find("hh:underline", NS)

    font_name = None
    if ref is not None and ref.get("hangul") is not None:
        i = _int_attr(ref, "hangul")
        if i is not None and 0 <= i < len(fonts_hangul):
            font_name = fonts_hangul[i]

    return CharPr(
        id=el.get("id"),
        height=_int_attr(el, "height"),
        text_color=el.get("textColor"),
        bold=el.find("hh:bold", NS) is not None,
        italic=el.find("hh:italic", NS) is not None,
        underline=(ul is not None and ul.get("type") not in (None, "NONE")),
        ratio=_int_attr(ratio, "hangul"),
        spacing=_int_attr(spacing, "hangul"),
        font_hangul=font_name,
    )


def _parse_border_fill(el) -> BorderFill:
    def w(tag):
        b = el.find("hh:%s" % tag, NS)
        return b.get("width") if b is not None else None

    brush = el.find(".//hc:winBrush", NS)
    fill = brush.get("faceColor") if brush is not None else None
    # 투명(alpha=0)이거나 흰색이면 '채움 없음'으로 본다.
    if fill in ("none", None):
        fill = None
    elif brush is not None and brush.get("alpha") == "0" and fill == "#FFFFFF":
        fill = None

    return BorderFill(id=el.get("id"), left=w("leftBorder"), right=w("rightBorder"),
                      top=w("topBorder"), bottom=w("bottomBorder"), fill=fill)


def build(header_xml: bytes) -> HeaderIndex:
    """header.xml 바이트 → HeaderIndex."""
    root = etree.fromstring(header_xml)
    idx = HeaderIndex()
    idx.fonts_hangul = _parse_fonts(root)

    for el in root.iter("{%s}paraPr" % NS['hh']):
        idx.para_pr[el.get("id")] = _parse_para_pr(el)
    for el in root.iter("{%s}charPr" % NS['hh']):
        idx.char_pr[el.get("id")] = _parse_char_pr(el, idx.fonts_hangul)
    for el in root.iter("{%s}borderFill" % NS['hh']):
        idx.border_fill[el.get("id")] = _parse_border_fill(el)
    for el in root.iter("{%s}style" % NS['hh']):
        idx.style[el.get("id")] = Style(
            id=el.get("id"), name=el.get("name"), eng_name=el.get("engName"),
            para_pr=el.get("paraPrIDRef"), char_pr=el.get("charPrIDRef"))
    for el in root.iter("{%s}bullet" % NS['hh']):
        idx.bullets[el.get("id")] = el.get("char")
    for el in root.iter("{%s}numbering" % NS['hh']):
        idx.numberings[el.get("id")] = [
            (h.text or "") for h in el.findall("hh:paraHead", NS)]
    for el in root.iter("{%s}tabPr" % NS['hh']):
        idx.tab_pr_ids.append(el.get("id"))

    # ── 무결성 점검 ──
    for tag, store in (("paraProperties", idx.para_pr),
                       ("charProperties", idx.char_pr),
                       ("borderFills", idx.border_fill),
                       ("styles", idx.style)):
        el = root.find(".//hh:%s" % tag, NS)
        if el is None:
            continue
        declared = _int_attr(el, "itemCnt")
        idx.item_counts[tag] = declared
        if declared is not None and declared != len(store):
            idx.warnings.append(
                f"{tag}: itemCnt={declared} 인데 실제 자식 {len(store)}개")

    if idx.border_fill:
        ids = sorted(map(int, idx.border_fill))
        if ids[0] != 1:
            idx.warnings.append(
                f"borderFill 시작 id가 {ids[0]} (샘플 양식은 1-base). 검증기 범위 확인 필요")

    # hp:default == hp:case × 2 관계 검증 (다른 양식에서 깨질 수 있다)
    broken = [pid for pid, p in idx.para_pr.items()
              if p.indent_left and p.default_left
              and p.default_left != p.indent_left * 2]
    if broken:
        idx.warnings.append(
            f"hp:default != hp:case×2 인 paraPr {len(broken)}개: {sorted(broken, key=int)[:8]}")

    no_switch = [pid for pid, p in idx.para_pr.items() if p.default_left is None
                 and p.indent_left is not None]
    if len(no_switch) == len(idx.para_pr):
        idx.warnings.append("hp:switch를 가진 paraPr이 하나도 없다 — 파싱 경로 확인 필요")

    return idx


def from_hwpx(path: str) -> HeaderIndex:
    with zipfile.ZipFile(path) as z:
        return build(z.read("Contents/header.xml"))
