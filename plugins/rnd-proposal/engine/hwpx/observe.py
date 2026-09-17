# -*- coding: utf-8 -*-
"""section0.xml 관측기 — 문단 하나하나를 '무엇으로 쓰였는가' 판단 가능한 레코드로.

역할 추론(infer_roles.py)은 header.xml의 정의만으로는 못 한다. 정의는 43개
paraPr이 다 있다고만 알려줄 뿐, 그중 무엇이 대제목이고 무엇이 표 안에서만
쓰이는지는 **본문에서 실제로 어떻게 쓰였는지**를 봐야 안다.

핵심 규칙 2가지 (docs/hwpx_format_notes.md §5):
  1. charPr은 문단의 '첫 텍스트 run' 기준이다. 마지막 run을 잡으면 소제목이
     charPr 29(빨강 "(○○연 담당 표시)")로 오판된다.
  2. 그림/표 앵커 문단은 hp:t가 없다. 이 경우 첫 run의 charPrIDRef로 폴백해야
     한다 — 그 값이 lineseg spacing 계산의 기준이 된다.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field

from lxml import etree

from .consts import NS

_P = "{%s}p" % NS['hp']
_TC = "{%s}tc" % NS['hp']
_CAPTION = "{%s}caption" % NS['hp']
_TBL = "{%s}tbl" % NS['hp']
_PIC = "{%s}pic" % NS['hp']
_T = "{%s}t" % NS['hp']
_MEMO = "{%s}memo" % NS['hp']
_MEMO_GROUP = "{%s}memogroup" % NS['hp']
_FIELD_BEGIN = "{%s}fieldBegin" % NS['hp']


@dataclass
class LineSeg:
    horzpos: int
    horzsize: int
    vertsize: int
    textheight: int
    baseline: int
    spacing: int
    flags: int


@dataclass
class Obs:
    """문단 하나의 관측 레코드."""
    index: int
    para: str | None
    style: str | None
    char: str | None                    # 첫 텍스트 run (없으면 첫 run 폴백)
    char_is_fallback: bool              # 텍스트 없이 폴백으로 얻었는가
    chars_all: list[str]                # run별 charPrIDRef 전체
    text: str
    in_table: bool                      # 표 셀의 '직접' 문단 (메모 등 중첩 제외)
    in_caption: bool
    in_memo: bool
    cell_row: int | None
    cell_col: int | None
    has_pic: bool
    has_tbl: bool
    lineseg: LineSeg | None
    caption_owner: str | None = None    # 'pic' | 'tbl' | None
    auto_num_type: str | None = None    # PICTURE | TABLE | ...

    @property
    def is_body(self) -> bool:
        return not self.in_table and not self.in_caption and not self.in_memo

    @property
    def is_anchor(self) -> bool:
        return self.has_pic or self.has_tbl


@dataclass
class Observation:
    paras: list[Obs] = field(default_factory=list)
    text_width_observed: int | None = None
    tables: list[dict] = field(default_factory=list)
    markpen_count: int = 0
    memo_count: int = 0
    colored_runs: list[tuple[str, str]] = field(default_factory=list)  # (charPr, text)
    memo_texts: list[str] = field(default_factory=list)      # 검토 코멘트 = 작성 지침
    markpen_texts: list[str] = field(default_factory=list)   # 형광펜 = 주의 지점
    run_texts: list[tuple[str, str, int]] = field(default_factory=list)  # (charPr, text, para#)
    prologue_run_raw: str | None = None
    first_para_attrs: dict = field(default_factory=dict)

    # ── 집계 편의 ──
    def body(self) -> list[Obs]:
        return [o for o in self.paras if o.is_body]

    def usage_by_para(self) -> dict[str, dict[str, int]]:
        """paraPr → {'body': n, 'table': n, 'caption': n, 'memo': n}"""
        out: dict[str, dict[str, int]] = {}
        for o in self.paras:
            if not o.para:
                continue
            d = out.setdefault(o.para,
                               {"body": 0, "table": 0, "caption": 0, "memo": 0})
            if o.in_memo:
                d["memo"] += 1
            elif o.in_caption:
                d["caption"] += 1
            elif o.in_table:
                d["table"] += 1
            else:
                d["body"] += 1
        return out


# ── 헬퍼 ───────────────────────────────────────────────────────────
def _first_text_char(p) -> tuple[str | None, bool]:
    """(charPrIDRef, is_fallback)."""
    for run in p.findall("hp:run", NS):
        for t in run.findall("hp:t", NS):
            if (t.text or "").strip():
                return run.get("charPrIDRef"), False
    for run in p.findall("hp:run", NS):           # 객체 앵커 폴백
        if run.get("charPrIDRef"):
            return run.get("charPrIDRef"), True
    return None, False


def _text(p) -> str:
    """이 문단 '자신의' 텍스트만. 중첩 객체 안으로 내려가지 않는다.

    ★ p.iter(hp:t)를 그냥 쓰면 표 앵커 문단이 표 안 모든 셀 텍스트를 자기
    텍스트로 삼는다. 그러면 skeleton.md에 '단계산출물1단계2단계' 같은
    괴상한 목차 항목이 생긴다(실제로 발생했다).
    """
    out = []
    for run in p.findall("hp:run", NS):
        for t in run.findall("hp:t", NS):
            out.append(t.text or "")
    return "".join(out).strip()


def _lineseg(p) -> LineSeg | None:
    ls = p.find("hp:linesegarray/hp:lineseg", NS)
    if ls is None:
        return None
    g = lambda k: int(ls.get(k))
    return LineSeg(g("horzpos"), g("horzsize"), g("vertsize"),
                   g("textheight"), g("baseline"), g("spacing"), g("flags"))


def _cell_addr(p):
    """표 셀의 '직접' 문단이면 (row, col), 아니면 (None, None).

    ★ 조상을 끝까지 훑으면 안 된다. 이 양식은 메모(hp:memo)가 표 셀 안에
    앵커돼 있어서, 조상 탐색으로는 메모 본문(styleIDRef=13, paraPr 1)이
    'rowAddr=0 셀 문단'으로 잡히고 표 머리행 역할이 오판된다.

    정규 경로는 tc → subList → p 뿐이므로 조부모만 확인한다.
    """
    parent = p.getparent()
    if parent is None:
        return None, None
    grand = parent.getparent()
    if grand is None or grand.tag != _TC:
        return None, None
    addr = grand.find("hp:cellAddr", NS)
    if addr is None:
        return None, None
    return int(addr.get("rowAddr")), int(addr.get("colAddr"))


def _field_ancestor(p):
    """필드(메모/각주 등) 안의 문단인지. 안이면 그 필드의 type을 돌려준다.

    실측: 메모 본문은 hp:memo가 아니라
        hp:fieldBegin[@type="MEMO"] → hp:subList → hp:p
    구조로 들어 있다. 조상에서 hp:memo만 찾으면 절대 못 잡는다.
    이 문단들은 본문이 아니므로 역할 추론에서 반드시 빼야 한다
    (안 빼면 body 역할이 메모 서식 paraPr 1 / style 13으로 오판된다).
    """
    for anc in p.iterancestors():
        if anc.tag == _FIELD_BEGIN:
            return anc.get("type") or "FIELD"
        if anc.tag in (_MEMO, _MEMO_GROUP):
            return "MEMO"
    return None


def _caption_owner(p) -> str | None:
    """캡션이 그림의 것인지 표의 것인지."""
    for anc in p.iterancestors():
        if anc.tag == _CAPTION:
            parent = anc.getparent()
            if parent is None:
                return None
            if parent.tag == _PIC:
                return "pic"
            if parent.tag == _TBL:
                return "tbl"
            return None
    return None


def _slice_prologue_run(raw: str) -> str | None:
    """첫 hp:run 원문을 정규식이 아니라 문자열 인덱스로 잘라낸다.

    lxml로 파싱 후 재직렬화하면 네임스페이스 접두사 순서와 따옴표가 바뀔 수
    있다. secPr은 페이지 여백·각주·쪽테두리 설정을 통째로 담고 있으므로
    **원문 바이트 그대로** 보존해야 안전하다.
    """
    start = raw.find("<hp:run")
    if start < 0:
        return None
    end = raw.find("</hp:run>", start)
    if end < 0:
        return None
    chunk = raw[start:end + len("</hp:run>")]
    return chunk if "<hp:secPr" in chunk else None


# ── 메인 ───────────────────────────────────────────────────────────
def build(section_xml: bytes) -> Observation:
    raw = section_xml.decode("utf-8", errors="replace")
    root = etree.fromstring(section_xml)
    obs = Observation()

    obs.prologue_run_raw = _slice_prologue_run(raw)

    max_end = 0
    for i, p in enumerate(root.iter(_P)):
        anc_tags = {a.tag for a in p.iterancestors()}
        row, col = _cell_addr(p)
        char, fallback = _first_text_char(p)
        ls = _lineseg(p)
        in_caption = _CAPTION in anc_tags
        field_type = _field_ancestor(p)
        in_memo = field_type is not None

        auto_num = p.find(".//hp:autoNum", NS)

        rec = Obs(
            index=i,
            para=p.get("paraPrIDRef"),
            style=p.get("styleIDRef"),
            char=char,
            char_is_fallback=fallback,
            chars_all=[r.get("charPrIDRef") for r in p.findall("hp:run", NS)],
            text=_text(p),
            in_table=row is not None,
            in_caption=in_caption,
            in_memo=in_memo,
            cell_row=row,
            cell_col=col,
            has_pic=p.find(".//hp:pic", NS) is not None,
            has_tbl=p.find("hp:run/hp:tbl", NS) is not None,
            lineseg=ls,
            caption_owner=_caption_owner(p) if in_caption else None,
            auto_num_type=auto_num.get("numType") if auto_num is not None else None,
        )
        obs.paras.append(rec)

        if field_type == "MEMO" and rec.text:
            obs.memo_texts.append(rec.text)

        if ls and rec.is_body:
            max_end = max(max_end, ls.horzpos + ls.horzsize)

        if i == 0:
            obs.first_para_attrs = {
                k: p.get(k) for k in
                ("paraPrIDRef", "styleIDRef", "pageBreak", "columnBreak", "merged")
                if p.get(k) is not None}

    obs.text_width_observed = max_end or None

    # 표 구조
    for tb in root.iter(_TBL):
        sz = tb.find("hp:sz", NS)
        cells = {}
        for tc in tb.iter(_TC):
            addr = tc.find("hp:cellAddr", NS)
            szc = tc.find("hp:cellSz", NS)
            if addr is None:
                continue
            cells[(int(addr.get("rowAddr")), int(addr.get("colAddr")))] = {
                "border_fill": tc.get("borderFillIDRef"),
                "width": int(szc.get("width")) if szc is not None else None,
                "height": int(szc.get("height")) if szc is not None else None,
            }
        obs.tables.append({
            "rows": int(tb.get("rowCnt")), "cols": int(tb.get("colCnt")),
            "width": int(sz.get("width")) if sz is not None else None,
            "border_fill": tb.get("borderFillIDRef"),
            "repeat_header": tb.get("repeatHeader"),
            "page_break": tb.get("pageBreak"),
            "cell_spacing": tb.get("cellSpacing"),
            "cells": cells,
        })

    # 양식 오염 흔적 (rev2 잔재) — 동시에 guidance.md의 원천이다
    obs.markpen_count = len(list(root.iter("{%s}markpenBegin" % NS['hp'])))
    obs.memo_count = sum(
        1 for f in root.iter("{%s}fieldBegin" % NS['hp'])
        if f.get("type") == "MEMO")

    # 형광펜 구간 텍스트: markpenBegin ~ markpenEnd 사이 형제 노드의 hp:t
    mp_begin = "{%s}markpenBegin" % NS['hp']
    mp_end = "{%s}markpenEnd" % NS['hp']
    for beg in root.iter(mp_begin):
        buf = []
        for sib in beg.itersiblings():
            if sib.tag == mp_end:
                break
            buf.extend(t.text or "" for t in sib.iter(_T))
        text = "".join(buf).strip()
        if text:
            obs.markpen_texts.append(text[:120])

    # run 단위 텍스트 (유색 charPr = 양식 작성 안내문 추출용)
    for i, p in enumerate(root.iter(_P)):
        for run in p.findall("hp:run", NS):
            t = "".join(x.text or "" for x in run.findall("hp:t", NS)).strip()
            if t and run.get("charPrIDRef"):
                obs.run_texts.append((run.get("charPrIDRef"), t[:120], i))

    return obs


def from_hwpx(path: str) -> Observation:
    with zipfile.ZipFile(path) as z:
        return build(z.read("Contents/section0.xml"))
