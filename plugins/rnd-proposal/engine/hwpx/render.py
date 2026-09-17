# -*- coding: utf-8 -*-
"""블록 IR + profile → section0.xml 문자열.

XML은 lxml로 만들지 않고 **문자열로 조립**한다. 이유:
  - 원본 section0.xml은 요소 사이에 개행이 없다. 재직렬화하면 공백이 끼거나
    네임스페이스 접두사 순서가 바뀐다.
  - prologue_run(secPr)은 원문 바이트를 그대로 삽입해야 한다.

절대 규칙 2가지:
  1. 본문 텍스트에 ◦ - ▪ 를 직접 넣지 않는다 (paraPr의 heading이 자동 렌더).
  2. 들여쓰기를 공백으로 흉내내지 않는다 (paraPr.margin.left가 담당).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .mdblocks import Block

XML_ESC = str.maketrans({"&": "&amp;", "<": "&lt;", ">": "&gt;",
                         '"': "&quot;", "'": "&apos;"})


def esc(t: str) -> str:
    return (t or "").translate(XML_ESC)


def half_up(x: float) -> int:
    return math.floor(x + 0.5)


class IdGen:
    """시드 고정 순차 채번. 난수를 쓰면 같은 입력이 매번 다른 바이트를 낸다."""

    def __init__(self, profile):
        pol = profile.data.get("id_policy", {})
        self.shape = int(pol.get("shape_id_base", 2100000000))
        self.instid = int(pol.get("instid_base", 1030000000))
        self.step = int(pol.get("step", 17))
        self.body_id = str(pol.get("para_id_body", "0"))
        self.tbl_id = str(pol.get("para_id_in_table", "2147483648"))
        self._n = 0

    def next_shape(self) -> tuple[str, str, int]:
        z = self._n
        s = self.shape + self._n * self.step
        i = self.instid + self._n * self.step
        self._n += 1
        return str(s), str(i), z


@dataclass
class RenderCtx:
    profile: object
    ids: IdGen
    warnings: list
    text_width: int


# ── 문단 ───────────────────────────────────────────────────────────
def _lineseg(ctx: RenderCtx, role: dict, vertsize: int | None = None,
             horzpos: int | None = None, horzsize: int | None = None) -> str:
    ch = int(role.get("char_height") or 1000)
    pct = int(role.get("line_spacing_pct") or 100)
    vs = vertsize if vertsize is not None else ch
    hp = horzpos if horzpos is not None else int(role.get("indent_left") or 0)
    hs = horzsize if horzsize is not None else (ctx.text_width - hp)
    flags = ctx.profile.data["lineseg"]["flags"]
    has_bullet = bool((role.get("heading") or {}).get("type") in ("BULLET", "OUTLINE")
                      or role.get("bullet_char"))
    return (f'<hp:linesegarray><hp:lineseg textpos="0" vertpos="0" '
            f'vertsize="{vs}" textheight="{vs}" baseline="{half_up(vs * 0.85)}" '
            f'spacing="{half_up(ch * (pct - 100) / 100)}" horzpos="{hp}" '
            f'horzsize="{hs}" flags='
            f'"{flags["with_bullet"] if has_bullet else flags["normal"]}"/>'
            f'</hp:linesegarray>')


def paragraph(ctx: RenderCtx, role_key: str, text: str = "", *,
              inner: str = "", pid: str | None = None,
              in_table: bool = False, page_break: str = "0",
              vertsize: int | None = None, horzpos: int | None = None,
              horzsize: int | None = None, prologue: str = "",
              emit_lineseg: bool = True) -> str:
    """hp:p 하나. inner를 주면 텍스트 대신 그 XML(hp:tbl/hp:pic)을 담는다."""
    r = ctx.profile.role(role_key)
    if not r.get("para"):
        ctx.warnings.append(f"역할 '{role_key}'이 해소되지 않아 body로 대체")
        r = ctx.profile.role("body")
    pid = pid or (ctx.ids.tbl_id if in_table else ctx.ids.body_id)
    char = r.get("char") or "0"
    style = r.get("style")
    style = "0" if style is None else str(style)

    body = prologue
    if inner:
        body += f'<hp:run charPrIDRef="{char}">{inner}</hp:run>'
    else:
        body += (f'<hp:run charPrIDRef="{char}"><hp:t>{esc(text)}</hp:t></hp:run>'
                 if text else f'<hp:run charPrIDRef="{char}"><hp:t/></hp:run>')

    ls = _lineseg(ctx, r, vertsize, horzpos, horzsize) if emit_lineseg else ""
    return (f'<hp:p id="{pid}" paraPrIDRef="{r["para"]}" styleIDRef="{style}" '
            f'pageBreak="{page_break}" columnBreak="0" merged="0">{body}{ls}</hp:p>')


def empty_paragraph(ctx: RenderCtx) -> str:
    return paragraph(ctx, "body", "")


# ── 표 ─────────────────────────────────────────────────────────────
def _display_width(s: str) -> int:
    """한글 2, 그 외 1."""
    return sum(2 if ord(c) > 0x1100 else 1 for c in s)


def column_widths(rows: list[list[str]], total: int, min_w: int = 2000) -> list[int]:
    """열 폭 배분. **잔차를 마지막 열에 몰아 합계 오차를 0으로 만든다.**

    Σ cellSz.width == tbl width 는 검증기 L3의 불변식이다.
    """
    ncol = len(rows[0])
    raw = []
    for c in range(ncol):
        w = max(_display_width(r[c]) for r in rows)
        raw.append(max(4, min(w, 40)))
    s = sum(raw) or 1
    out = [max(min_w, round(total * x / s)) for x in raw[:-1]]
    last = total - sum(out)
    if last < min_w:                      # 마지막이 너무 좁으면 앞에서 덜어온다
        deficit = min_w - last
        for i in range(len(out)):
            take = min(deficit, out[i] - min_w)
            out[i] -= take
            deficit -= take
            if deficit <= 0:
                break
        last = total - sum(out)
    out.append(last)
    return out


def _row_height(cells: list[str], widths: list[int], role: dict,
                in_margin: dict, default_h: int) -> int:
    ch = int(role.get("char_height") or 800)
    pct = int(role.get("line_spacing_pct") or 100)
    lines = 1
    for txt, w in zip(cells, widths):
        inner = max(w - in_margin["left"] - in_margin["right"], 1)
        need = _display_width(txt) * (ch / 2)
        lines = max(lines, math.ceil(need / inner) if inner else 1)
    return max(default_h, int(lines * ch * pct / 100) + 400)


def table(ctx: RenderCtx, rows: list[list[str]], resolver) -> tuple[str, dict]:
    """hp:tbl. 반환 (xml, meta)."""
    prof = ctx.profile
    t = prof.table
    nrow, ncol = len(rows), len(rows[0])
    total = min(int(t.get("width_budget") or ctx.text_width), ctx.text_width)
    widths = column_widths(rows, total)
    im = {k: int(v) for k, v in (t.get("in_margin")
                                 or {"left": 510, "right": 510,
                                     "top": 141, "bottom": 141}).items()}
    grid = resolver.grid(nrow, ncol)
    ctx.warnings.extend(grid.warnings)
    ctx.warnings.extend(grid.fallbacks)

    hdr_role = prof.role("table_header")
    cell_role = prof.role("table_cell")
    default_h = int(t.get("default_row_height", 1386))

    trs = []
    heights = []
    for r in range(nrow):
        role = hdr_role if (r == 0) else cell_role
        h = _row_height(rows[r], widths, role, im, default_h)
        heights.append(h)
        tcs = []
        for c in range(ncol):
            bf = grid.grid.get((r, c), (t.get("tbl_border_fill") or resolver.default_id()))
            hs = widths[c] - im["left"] - im["right"]
            # ★ 셀에는 linesegarray를 넣지 않는다 (실측 결함, 2026-08-19).
            #   캡션과 같은 원인이다 — lineseg를 한 줄만 주면 한글이 줄바꿈된
            #   나머지 줄을 **같은 vertpos에 겹쳐 찍는다**. 실렌더에서
            #   "(연도별) N억원 (총) M억원" 셀이 두 줄로 뭉개진 것을 확인했다.
            #   셀 줄 수는 열 폭·글꼴에 의존해 미리 알 수 없으므로 한글이 계산한다.
            p = paragraph(ctx, "table_header" if r == 0 else "table_cell",
                          rows[r][c], in_table=True, horzpos=0, horzsize=hs,
                          emit_lineseg=False)
            tcs.append(
                f'<hp:tc name="" header="{1 if r == 0 else 0}" hasMargin="0" '
                f'protect="0" editable="0" dirty="0" borderFillIDRef="{bf}">'
                f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" '
                f'vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" '
                f'textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                f'{p}</hp:subList>'
                f'<hp:cellAddr colAddr="{c}" rowAddr="{r}"/>'
                f'<hp:cellSpan colSpan="1" rowSpan="1"/>'
                f'<hp:cellSz width="{widths[c]}" height="{h}"/>'
                f'<hp:cellMargin left="600" right="600" top="400" bottom="400"/>'
                f'</hp:tc>')
        trs.append("<hp:tr>" + "".join(tcs) + "</hp:tr>")

    sid, _, z = ctx.ids.next_shape()
    tbl_h = sum(heights)
    xml = (f'<hp:tbl id="{sid}" zOrder="{z}" numberingType="TABLE" '
           f'textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" '
           f'dropcapstyle="None" pageBreak="{t.get("page_break", "CELL")}" '
           f'repeatHeader="{t.get("repeat_header", 1)}" rowCnt="{nrow}" '
           f'colCnt="{ncol}" cellSpacing="{t.get("cell_spacing", 0)}" '
           f'borderFillIDRef="{(t.get("tbl_border_fill") or resolver.default_id())}" noAdjust="0">'
           f'<hp:sz width="{total}" widthRelTo="ABSOLUTE" height="{tbl_h}" '
           f'heightRelTo="ABSOLUTE" protect="0"/>'
           f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" '
           f'allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" '
           f'horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" '
           f'horzOffset="0"/>'
           f'<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
           f'<hp:inMargin left="{im["left"]}" right="{im["right"]}" '
           f'top="{im["top"]}" bottom="{im["bottom"]}"/>'
           + "".join(trs) + "</hp:tbl>")
    return xml, {"width": total, "height": tbl_h, "widths": widths,
                 "rows": nrow, "cols": ncol}


# ── 그림 ───────────────────────────────────────────────────────────
def picture(ctx: RenderCtx, geo: dict, bin_id: str, caption: str,
            caption_num: int, filename: str) -> str:
    """hp:pic + hp:caption(자동채번).

    geo는 figure.geometry()가 만든 dict.
    """
    prof = ctx.profile
    fig = prof.figure
    cap_cfg = fig.get("caption", {})
    sid, iid, z = ctx.ids.next_shape()

    cw, chh = geo["curSz"]
    ow, oh = geo["orgSz"]
    dw, dh = geo["imgDim"]
    e1, e5 = geo["scaMatrix"]

    cap_xml = ""
    if caption:
        cr = prof.role(cap_cfg.get("role", "figure_caption"))
        cch = int(cr.get("char_height") or 1000)
        cap_p = (
            f'<hp:p id="0" paraPrIDRef="{cr.get("para")}" '
            f'styleIDRef="{cr.get("style") if cr.get("style") is not None else 0}" '
            f'pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="{cr.get("char")}">'
            f'<hp:t>{esc(cap_cfg.get("prefix", "그림 "))}</hp:t>'
            f'<hp:ctrl><hp:autoNum num="{caption_num}" '
            f'numType="{cap_cfg.get("auto_num_type") or "PICTURE"}">'
            f'<hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" '
            f'suffixChar="" supscript="0"/></hp:autoNum></hp:ctrl>'
            f'<hp:t>. {esc(caption)}</hp:t></hp:run></hp:p>')
        # ★ 캡션에는 linesegarray를 넣지 않는다 (실측 결함, 2026-08-18).
        #   lineseg를 한 줄만 주면 한글이 그 한 줄을 그대로 믿고, 줄바꿈된
        #   나머지 줄을 **같은 vertpos에 겹쳐 찍는다**. 한글 실렌더 PDF에서
        #   3줄짜리 캡션이 한 줄 위에 뭉개진 것을 확인했다.
        #   캡션은 줄 수를 미리 알 수 없으므로(폭·글꼴 의존) 한글이 계산하게
        #   맡긴다. vendor의 _strip_linesegarray() 폴백이 증명하듯 없어도 열린다.
        # ★ width는 그림 폭(curSz)을 따라가야 한다. 고정값을 쓰면 캡션이
        #   그림보다 좁은 칸에 갇혀 세로로 눌린다(2번 양식에서 실측).
        cap_xml = (
            f'<hp:caption side="{cap_cfg.get("side") or "BOTTOM"}" fullSz="0" '
            f'width="{cw}" '
            f'gap="{cap_cfg.get("gap", 850)}" lastWidth="{cw}">'
            f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" '
            f'vertAlign="TOP" linkListIDRef="0" linkListNextIDRef="0" '
            f'textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
            f'{cap_p}</hp:subList></hp:caption>')

    return (
        f'<hp:pic id="{sid}" zOrder="{z}" instid="{iid}" reverse="0" '
        f'numberingType="PICTURE" textWrap="TOP_AND_BOTTOM" '
        f'textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" href="" '
        f'groupLevel="0">'
        f'<hp:offset x="0" y="0"/>'
        f'<hp:orgSz width="{ow}" height="{oh}"/>'
        f'<hp:curSz width="{cw}" height="{chh}"/>'
        f'<hp:flip horizontal="0" vertical="0"/>'
        f'<hp:rotationInfo angle="0" centerX="{cw // 2}" centerY="{chh // 2}" '
        f'rotateimage="1"/>'
        f'<hp:renderingInfo>'
        f'<hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
        f'<hc:scaMatrix e1="{e1:.6f}" e2="0" e3="0" e4="0" e5="{e5:.6f}" e6="0"/>'
        f'<hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
        f'</hp:renderingInfo>'
        f'<hc:img binaryItemIDRef="{bin_id}" bright="0" contrast="0" '
        f'effect="REAL_PIC" alpha="0"/>'
        f'<hp:imgRect><hc:pt0 x="0" y="0"/><hc:pt1 x="{ow}" y="0"/>'
        f'<hc:pt2 x="{ow}" y="{oh}"/><hc:pt3 x="0" y="{oh}"/></hp:imgRect>'
        f'<hp:imgClip left="0" right="{dw}" top="0" bottom="{dh}"/>'
        f'<hp:inMargin left="0" right="0" top="0" bottom="0"/>'
        f'<hp:imgDim dimwidth="{dw}" dimheight="{dh}"/>'
        f'<hp:effects/>'
        f'<hp:sz width="{cw}" widthRelTo="ABSOLUTE" height="{chh}" '
        f'heightRelTo="ABSOLUTE" protect="0"/>'
        f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" '
        f'allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" '
        f'horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" '
        f'horzOffset="0"/>'
        f'<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
        f'{cap_xml}'
        f'<hp:shapeComment>{esc(filename)} {geo["px"][0]}x{geo["px"][1]}'
        f'</hp:shapeComment></hp:pic>')


# ── 블록 → 역할 매핑 ───────────────────────────────────────────────
def role_for(block: Block, prof) -> str:
    if block.kind == "heading":
        return f"heading_{min(block.level, 3)}"
    if block.kind == "bullet":
        maxd = int(prof.writing_rules.get("max_bullet_depth", 3))
        lvl = min(block.level, maxd - 1)
        return f"bullet_level_{lvl}"
    return "body"
