"""양식 첫머리(참고 상자 · 표지 제목 · 개요표)를 **원본 그대로** 싣고 값 칸만 채운다.

## 왜 생겼나 (2026-09-17 사용자 지시)

다른 PC 에서 NST 전략연구사업 양식으로 만든 계획서의 개요가 **무너져 있었다.**
양식의 개요는 35행×10열 병합 표 하나인데, 산출물은 그걸 버리고 2열짜리 표
4개를 새로 만들었다. 표지의 「01 ← 연번 + 과제명」 상자도 빠졌다.

원인은 조립 방식이다. 엔진은 원고의 마크다운 표를 **새 표로 짓는다.** 원본 표의
칸을 채우는 경로가 없었다(vendor/cell_writer.py 는 있었지만 아무도 부르지 않았다).

## 방식

양식 폴더에 `overview_fill.yaml` 이 있으면 켜진다. 없으면 엔진은 예전대로 돈다.

    원본 section0 최상위 문단 0 … front-1   바이트 그대로(표지·개요)
      └ 표지 상자  : 연번 · 과제명 칸만 고친다
      └ 개요표     : 값 칸을 원고 값으로 **덮어쓰거나 비운다**
    원고의 「개요」 구간                     표로 옮겼으니 본문에서 뺀다
    원고의 나머지                            엔진이 이어서 짓는다

## ★ 원고가 채우지 않은 값 칸은 비운다

이 저장소의 NST 양식 원본은 빈 양식이 아니라 **공동 작성 중인 초안**이다
(파란 글씨로 참여기관·사업비·과제 본문이 들어 있다). 칸을 남기면 남의 초안이
산출물로 샌다. 그래서 값 칸은 전부 「원고 값 또는 빈칸」 둘 중 하나가 된다.
라벨 칸(「국정과제」「비전」…)은 양식 구조이므로 건드리지 않는다.

글자모양도 원본 값 칸 것을 쓰지 않는다 — 그 칸들은 **파랑(#0000FF)** 이다.
명세의 `styles` 에 적힌 검정 모양으로 짓는다.
"""
from __future__ import annotations

import copy
import os
import re

import yaml
from lxml import etree

from .mdblocks import Block
from .vendor import zip_surgery

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS = {"hp": HP}
q = lambda t: f"{{{HP}}}{t}"          # noqa: E731


def load_spec(form_dir: str) -> dict | None:
    p = os.path.join(form_dir, "overview_fill.yaml")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def norm(s: str) -> str:
    """라벨 대조용 — 공백·가운뎃점·괄호·기호를 뺀다."""
    return re.sub(r"[\s·ㆍ\.\-_,:：()\[\]「」※*]", "", s or "")


# ── 원고 → 값 ──────────────────────────────────────────────────────────

def collect(blocks, spec):
    """개요 구간의 블록에서 (필드→줄, 연구비 머리글→값, 경고, 옮기지 못한 블록) 을 모은다.

    받는 모양:
      · 2열 표  | 구분 | 내용 |   — 구분이 빈 행은 윗 행의 이어지는 줄
      · 머리글이 키인 표  | 연번 | 과제명 |  — 다음 행이 값
      · 머리글에 「연구기간」이 든 표 — 연구기간·연구개발비 행
      · 「키: 값」 글머리/본문 한 줄
    **양식에 자리가 없는 표는 버리지 않고 돌려준다** — 엔진이 개요표 뒤에 그대로 싣는다.
    (실측: 예전 원고의 재무 성과 표가 경고만 남기고 사라졌다)
    """
    fields = spec["table"]["fields"]
    alias = {}
    for f in fields:
        for name in [f["key"], *(f.get("aliases") or [])]:
            alias[norm(name)] = f["key"]
    cover_num_key = norm(spec.get("cover", {}).get("number", {}).get("key", ""))
    # 2열 표의 행으로 쓴 연구비 — 「연구기간」「연구개발비(총액)」
    brow = {}
    for head, names in ((spec["table"].get("budget") or {}).get("row_aliases") or {}).items():
        for nm in names:
            brow[norm(nm)] = norm(head)

    values: dict[str, list[str]] = {}
    budget: dict[str, str] = {}
    warns: list[str] = []
    leftover: list = []

    def resolve(raw_key: str):
        k = norm(raw_key)
        if not k:
            return None
        if cover_num_key and k == cover_num_key:
            return "__연번__"
        if k in brow:
            return ("budget", brow[k])
        key = alias.get(k)
        if key is None:
            # 앞머리 일치 — 「연계 수요명(정부)」 같은 변형을 받는다
            key = next((v for a, v in alias.items() if k.startswith(a) or a.startswith(k)), None)
        return key

    def put(raw_key: str, text: str, last: list) -> bool:
        if not norm(raw_key):
            if last[0] is None:
                warns.append(f"개요: 구분 없는 첫 행 「{text[:30]}」")
                return False
            if isinstance(last[0], tuple):
                budget[last[0][1]] = (budget[last[0][1]] + " " + text).strip()
            else:
                values[last[0]].append(text)
            return True
        key = resolve(raw_key)
        if key is None:
            warns.append(f"개요: 양식에 없는 항목 「{raw_key}」 — 원고 표 그대로 개요표 뒤에 싣는다")
            last[0] = None
            return False
        if isinstance(key, tuple):
            budget[key[1]] = text
        elif key == "__연번__":
            values[key] = [text]
        else:
            got = values.setdefault(key, [])
            if text not in got:              # 열 방향 표와 2열 표에 같은 값이 겹칠 수 있다
                got.append(text)
        last[0] = key
        return True

    last = [None]
    for b in blocks:
        if b.kind == "table" and b.rows:
            head = [norm(c) for c in b.rows[0]]
            if any("연구기간" in h for h in head) and len(b.rows) >= 2:
                for h, v in zip(b.rows[0], b.rows[1]):
                    budget[norm(h)] = v.strip()
                continue
            # 머리글이 전부 아는 키면 열 방향 표다 (| 연번 | 과제명 |)
            if len(b.rows) >= 2 and len(head) >= 2 and all(resolve(h) for h in b.rows[0]):
                for h, v in zip(b.rows[0], b.rows[1]):
                    put(h, v.strip(), [None])
                continue
            has_head = norm(b.rows[0][0]) in ("구분", "항목")
            rows = b.rows[1:] if has_head else b.rows
            hit, miss = 0, []
            for r in rows:
                if len(r) >= 2 and put(r[0], " ".join(c for c in r[1:] if c).strip(), last):
                    hit += 1
                else:
                    miss.append(r)
            if not hit:
                leftover.append(b)
            elif miss:
                # 일부 행만 자리가 없으면 그 행들만 따로 표로 싣는다
                leftover.append(Block("table", rows=[b.rows[0] if has_head else ["구분", "내용"]] + miss,
                                      has_header=True))
        elif b.kind in ("bullet", "body"):
            m = re.match(r"^\s*([^:：]{2,20})\s*[:：]\s*(.+)$", b.text)
            if m and put(m.group(1), m.group(2).strip(), last):
                continue
            # 「아래 표와 같음」 같은 도입 문장은 버린다
        elif b.kind != "heading":
            leftover.append(b)
    return values, budget, warns, leftover


# ── 칸 쓰기 ────────────────────────────────────────────────────────────

def _cells(tbl) -> dict[tuple[int, int], etree._Element]:
    out = {}
    for tc in tbl.findall("hp:tr/hp:tc", NS):
        a = tc.find("hp:cellAddr", NS)
        out[(int(a.get("rowAddr")), int(a.get("colAddr")))] = tc
    return out


# 여러 줄 칸 높이 추정.
# ★ 실렌더로 잰 값이다(2026-09-17). 한글은 원본 칸 높이를 그대로 쓰고 **내용에 맞춰
#   늘려 주지 않았다** — 줄 수 × 1300 으로 낮췄더니 마지막 줄이 테두리에 걸렸다.
#   10pt · 130% 한 줄은 110dpi 렌더에서 약 16.4pt ≈ 1650 HWPUNIT 이었고,
#   칸 너비를 넘는 줄은 두 줄로 접혀서 줄 수도 모자랐다. 그래서 접힘까지 세고
#   반 줄 여유를 둔다. 넉넉한 쪽으로 틀리는 편이 낫다(잘리는 것보다 빈칸이 낫다).
LINE_H = 1700
CELL_PAD = 282 + 850
CHAR_W_WIDE = 1000      # 10pt 한글·전각
CHAR_W_NARROW = 560     # 10pt 영문·숫자·기호


def _visual_lines(lines: list[str], width: int) -> int:
    usable = max(1, width - 1100)            # 좌우 여백 + 글머리 들여쓰기
    n = 0
    for s in lines:
        w = sum(CHAR_W_WIDE if ord(ch) > 0x2E7F else CHAR_W_NARROW for ch in s)
        n += max(1, -(-w // usable))
    return max(1, n)


def _fit_rows(tbl, cells: dict, need: dict) -> None:
    """칸 높이를 내용에 맞추고 행 단위로 맞춘다.

    한 행의 한 줄짜리 칸들은 높이가 같아야 하고, 여러 행에 걸친 칸은 그 행들의
    합이어야 한다. 한글이 알아서 맞춰 주지 않으므로 여기서 계산한다.
    """
    spans = {}
    for k, tc in cells.items():
        sp = tc.find("hp:cellSpan", NS)
        spans[k] = (int(sp.get("rowSpan")) if sp is not None else 1)
    height = {k: int(tc.find("hp:cellSz", NS).get("height")) for k, tc in cells.items()}
    for k, (lines, can_shrink) in need.items():
        w = int(cells[k].find("hp:cellSz", NS).get("width"))
        vis = _visual_lines(lines, w)
        if can_shrink:
            height[k] = vis * LINE_H + CELL_PAD
        else:
            # 값 칸은 원본 높이가 이미 한 줄을 넉넉히 담는다 — 넘친 줄만큼만 늘린다.
            # (처음엔 여러 줄 칸과 같은 식을 썼더니 한 줄 칸이 전부 커져 표가 쪽을 넘었다)
            fit = max(1, (height[k] - 282) // 1150)
            height[k] += max(0, vis - fit) * LINE_H
    nrow = int(tbl.get("rowCnt"))
    row_h = [0] * nrow
    for (r, c), h in height.items():
        if spans[(r, c)] == 1:
            row_h[r] = max(row_h[r], h)
    # 여러 행 칸이 행 합보다 크면 차이를 마지막 행에 얹는다(원본 높이는 지킨다)
    for (r, c), h in height.items():
        rs = spans[(r, c)]
        if rs > 1:
            tot = sum(row_h[r:r + rs])
            if h > tot and (r, c) not in need:
                row_h[r + rs - 1] += h - tot
    for (r, c), tc in cells.items():
        tc.find("hp:cellSz", NS).set("height", str(sum(row_h[r:r + spans[(r, c)]])))
    tbl.find("hp:sz", NS).set("height", str(sum(row_h)))


def _new_para(proto, para: str, char: str, text: str):
    """원본 칸 문단을 틀로, 문단모양·글자모양을 명세 값으로 바꿔 한 줄을 짓는다."""
    p = copy.deepcopy(proto)
    p.set("paraPrIDRef", str(para))
    for child in list(p):
        p.remove(child)
    run = etree.SubElement(p, q("run"))
    run.set("charPrIDRef", str(char))
    t = etree.SubElement(run, q("t"))
    t.text = text
    # linesegarray 는 넣지 않는다 — 표 안 문단은 한글이 다시 계산한다
    # (tests/test_e2e.py::test_table_cells_have_no_linesegarray)
    return p


def write_cell(tc, lines: list[str], style: dict) -> None:
    sub = tc.find("hp:subList", NS)
    paras = sub.findall("hp:p", NS)
    proto = paras[0]
    for p in paras:
        sub.remove(p)
    for line in (lines or [""]):
        sub.append(_new_para(proto, style["para"], style["char"], line))


def bullets(lines: list[str]) -> list[str]:
    """여러 줄 칸: 양식이 글머리 문자를 **직접** 찍는 구간이다(자동 글머리 없음).

    원고의 1수준 → 「◦ 」, 2수준 이하(앞에 공백·「-」) → 「 - 」.
    이미 ◦·①…로 시작하면 그대로 둔다.
    """
    out = []
    for s in lines:
        raw = s.rstrip()
        body = raw.lstrip()
        if not body:
            continue
        if body[0] in "◦○●①②③④⑤⑥⑦⑧⑨⑩":
            out.append(body if body[0] != "○" else "◦" + body[1:])
        elif body.startswith(("- ", "* ", "· ")) or raw.startswith("  "):
            out.append(" - " + body.lstrip("-*· ").strip())
        else:
            out.append("◦ " + body)
    return out


def _tidy(para) -> None:
    """안내문을 걷어낸 자리에 남은 빈 괄호 「()」를 지운다.

    「공동·위탁연구개발기관(」「미해당 시 삭제」「)」처럼 괄호는 검정, 안은 파랑인
    경우가 있어 run 을 걷어내면 「()」가 남는다(실측).
    """
    ts = [t for t in para.iter(q("t"))]
    for t in ts:
        if t.text:
            t.text = re.sub(r"\(\s*\)", "", t.text)
    for a, b in zip(ts, ts[1:]):
        if (a.text or "").rstrip().endswith("(") and (b.text or "").lstrip().startswith(")"):
            a.text = a.text.rstrip()[:-1]
            b.text = b.text.lstrip()[1:]


# ── 조립 ──────────────────────────────────────────────────────────────

def front_paragraphs(template: str, spec: dict, values: dict, budget: dict
                     ) -> tuple[list[str], list[str]]:
    """(최상위 문단 XML 문자열 목록, 경고)."""
    import zipfile
    with zipfile.ZipFile(template) as z:
        sec = z.read("Contents/section0.xml")
    parts = zip_surgery.parse_section(sec)
    kids = zip_surgery.extract_children(parts.body)
    n = int(spec["front_paragraphs"])
    front = list(kids[:n])
    styles = spec["styles"]
    warns: list[str] = []
    # 초안 표시색 글자모양 — 라벨 칸에도 초안 작성자가 덧붙인 파란 글씨가 있었다
    # (「, 공동, 위탁은 추후 변경 가능」). 값 칸은 다시 쓰니 상관없고, 남는 칸에서 걷어낸다.
    colors = spec.get("draft_color") or []
    colors = [colors] if isinstance(colors, str) else list(colors)
    color = "·".join(colors)
    draft_chars: set[str] = set()
    if colors:
        with zipfile.ZipFile(template) as z:
            hdr = z.read("Contents/header.xml").decode("utf-8")
        for c in colors:
            draft_chars |= set(re.findall(
                rf'<hh:charPr id="(\d+)"[^>]*textColor="{re.escape(c)}"', hdr))

    def strip_draft(p):
        removed = 0
        for para in p.iter(q("p")):
            gone = 0
            for run in para.findall("hp:run", NS):
                keeps_object = (run.find("hp:tbl", NS) is not None
                                or run.find("hp:secPr", NS) is not None)
                if run.get("charPrIDRef") in draft_chars and not keeps_object:
                    para.remove(run)
                    gone += 1
            if gone:
                _tidy(para)
                if para.find("hp:run", NS) is None:
                    r = etree.SubElement(para, q("run"))
                    r.set("charPrIDRef", str(styles["value"]["char"]))
                # 안내문만 있던 줄은 줄째 뺀다 — 칸에 다른 줄이 있을 때만
                sub = para.getparent()
                if (not "".join(para.itertext()).strip() and sub is not None
                        and any("".join(x.itertext()).strip()
                                for x in sub.findall("hp:p", NS) if x is not para)):
                    sub.remove(para)
            removed += gone
        return removed

    def edit(idx: int, fn):
        # 섹션 머리(이름공간 선언)로 감싸 파싱하고, 감싼 껍데기만 걷어낸다
        doc = etree.fromstring((parts.xml_header + front[idx] + parts.root_close_tag).encode("utf-8"))
        fn(doc[0])
        if draft_chars:
            k = strip_draft(doc[0])
            if k:
                warns.append(f"첫머리 문단 {idx}: 초안 표시색({color}) 글자 {k}곳을 걷어냈다")
        s = etree.tostring(doc, encoding="unicode")
        front[idx] = s[s.index(">") + 1: s.rindex("</")]

    # 표지 상자
    cov = spec.get("cover")
    if cov:
        def fill_cover(p):
            cells = _cells(next(p.iter(q("tbl"))))
            title_lines = values.get(cov["title"]["from"]) or []
            title = re.sub(r"^\(\s*국문\s*\)\s*", "", title_lines[0]).strip() if title_lines else ""
            if not title:
                warns.append("표지: 과제명이 원고에 없어 제목 칸을 비웠다")
            write_cell(cells[tuple(cov["title"]["cell"])], [title], styles["title"])
            num = values.get("__연번__")
            if num:
                tc = cells[tuple(cov["number"]["cell"])]
                t = tc.find(".//hp:t", NS)
                t.text = num[0]
        edit(int(cov["paragraph"]), fill_cover)

    # 개요표
    tspec = spec["table"]

    need: dict = {}           # (행, 열) → (쓴 줄, 줄여도 되는가)

    def fill_table(p):
        tbl = next(p.iter(q("tbl")))
        cells = _cells(tbl)

        def put_cell(key, lines, style):
            write_cell(cells[key], lines, style)
            if any(x.strip() for x in lines):
                need[key] = (lines, False)          # 값 칸은 늘리기만 한다
        for f in tspec["fields"]:
            lines = list(values.get(f["key"]) or [])
            mode = f.get("mode", "cells")
            if mode == "block":
                key = tuple(f["cells"][0])
                body = bullets(lines)
                write_cell(cells[key], body, styles["block"])
                # ★ 원본 칸 높이는 초안 분량(13줄·58줄)에 맞춰 고정돼 있다. 그대로 두면
                #   네 줄을 써도 칸이 반 쪽을 차지한다(실렌더). 내용만큼으로 줄인다.
                need[key] = (body, True)
                continue
            if mode == "grid":
                rows, cols = f["rows"], f["cols"]
                for i, r in enumerate(rows):
                    parts_ = [""] * len(cols)
                    if i < len(lines):
                        segs = [x.strip() for x in lines[i].split(" / ")]
                        if len(segs) == len(cols):
                            parts_ = segs
                        else:
                            parts_[-1] = lines[i]
                    for c, v in zip(cols, parts_):
                        put_cell((r, c), [v], styles["value"])
                if len(lines) > len(rows):
                    warns.append(f"개요 「{f['key']}」: 칸 {len(rows)}줄보다 원고가 "
                                 f"{len(lines)}줄 길어 뒤를 마지막 칸에 붙였다")
                    put_cell((rows[-1], cols[-1]), lines[len(rows) - 1:],
                             styles["value"])
                continue
            targets = [tuple(c) for c in f["cells"]]
            if mode == "lines_in_cell":
                put_cell(targets[0], lines, styles["value"])
            else:
                for i, tgt in enumerate(targets):
                    if i == len(targets) - 1:
                        chunk = lines[i:]            # 남는 줄은 마지막 칸에 문단으로
                    else:
                        chunk = lines[i:i + 1]
                    put_cell(tgt, chunk, styles["value"])
            for c in f.get("clear") or []:
                write_cell(cells[tuple(c)], [""], styles["value"])

        b = tspec.get("budget")
        if b:
            hr, vr = int(b["header_row"]), int(b["value_row"])
            heads = {norm("".join(tc.itertext())): col
                     for (r, col), tc in cells.items() if r == hr}
            used = set()
            for h, v in budget.items():
                col = heads.get(h) or next((c for k, c in heads.items() if k.startswith(h) or h.startswith(k)), None)
                if col is None:
                    warns.append(f"연구비 표: 양식에 없는 머리글 「{h}」")
                    continue
                put_cell((vr, col), [v], styles["budget"])
                used.add(col)
            for (r, col), tc in cells.items():
                if r == vr and col not in used:
                    write_cell(tc, [""], styles["budget"])
        _fit_rows(tbl, cells, need)
    edit(int(tspec["paragraph"]), fill_table)

    # 편집하지 않은 첫머리 문단에도 초안 표시색이 있으면 걷어낸다
    done = {int(tspec["paragraph"])} | ({int(cov["paragraph"])} if cov else set())
    for idx in range(n):
        if idx not in done and any(f'charPrIDRef="{c}"' in front[idx] for c in draft_chars):
            edit(idx, lambda p: None)
    return front, warns
