"""양식 첫머리(표지 · 개요표)를 **원본 그대로** 싣고 값 칸만 채운다.

## 왜 생겼나 (2026-09-17 사용자 지시)

다른 PC 에서 NST 전략연구사업 양식으로 만든 계획서의 개요가 **무너져 있었다.**
양식의 개요는 35행×10열 병합 표 하나인데, 산출물은 그걸 버리고 2열짜리 표
4개를 새로 만들었다. 표지의 「01 ← 연번 + 과제명」 상자도 빠졌다.
엔진은 원고의 마크다운 표를 **새 표로 짓기만** 했다.

## 명세는 둘 중 하나

    forms/<id>/overview_fill.yaml   사람이 쓴 명세 — 있으면 이것이 이긴다
    derive_spec(template)           없으면 **양식을 읽고 스스로 만든다**

사용자 요구(2026-09-17): 「skills 안에서 알아서 양식을 따르게」. 양식마다 좌표를
손으로 적는 방식으로는 남의 PC 에서 새 양식을 넣었을 때 아무 소용이 없다.

## 자동 판정의 단서 — 음영

한국 공공 양식은 **라벨 칸에 음영**을 넣는다(실측: #F2F2F2·#D4D4D4·#D9D9D9).
값 칸은 음영이 없다. 음영이 빠진 라벨(초안에서 편집된 「국정과제」)은 같은 표의
음영 라벨과 **같은 위치·같은 폭**이면 라벨로 본다.

    한 행에서 라벨 오른쪽 칸들   → 그 라벨의 값 칸
    여러 행에 걸친 라벨          → 걸친 행마다 한 줄
    전폭 음영 제목 + 전폭 빈칸    → 여러 줄 칸(핵심 연구내용 같은)
    음영 칸만 3개 이상인 행 + 다음 행 → 머리글 행(연구기간·주관기관·…)

## 채우지 않은 값 칸

    수작업 명세  clear_unfilled: all     전부 비운다(원본이 초안인 걸 사람이 안다)
    자동 판정    clear_unfilled: guided  초안 색 · ※ 안내 · (예시) · 자리표시만 비운다

자동 판정이 전부 비우면 안 되는 이유(실측): `nst-rnd-plan` 표지표에는 음영 없는
**양식 고정 글자**가 있다(TRL 단계 눈금, 「[ ] 신청용 [ ] 협약용」). 지우면 양식이 깨진다.

## 원고가 양식과 안 맞으면 쓰지 않는다

자동 판정은 원고 개요에서 **3개 이상** 맞춰야 켜진다. 모자라면 예전처럼 원고 표를
새로 짓는다 — 엉뚱한 칸에 넣는 것보다 낫다.
"""
from __future__ import annotations

import copy
import os
import re
import zipfile
from collections import Counter

import yaml
from lxml import etree

from .mdblocks import Block
from .vendor import zip_surgery

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS = {"hp": HP}
q = lambda t: f"{{{HP}}}{t}"          # noqa: E731

MIN_MATCH_AUTO = 3                    # 자동 판정이 켜지는 최소 일치 항목 수
GUIDE_BOX = re.compile(r"작성\s*요령|제출\s*시\s*삭제|유의\s*사항|작성\s*방법|제출\s*서류")
PLACEHOLDER = re.compile(r"^[\s\(\)]*$|000|○○○|OOO|XX|^\s*\((부서명|직함|성함|전화번호|e-mail)\)")
NUM_HEADING = re.compile(r"^\s*(\d+)\s*[\.\)]\s*\S")


def norm(s: str) -> str:
    """라벨 대조용 — 공백·가운뎃점·괄호·기호를 뺀다."""
    return re.sub(r"[\s·ㆍ\.\-_,:：()\[\]「」※*]", "", s or "")


def clean_label(s: str) -> str:
    """라벨 글자에서 안내 꼬리를 뗀다 — 「연계 수요명※ 수요 적합도…」「정부수요(예시)」."""
    s = re.sub(r"※.*$", "", s or "", flags=re.S)
    s = re.sub(r"\((예시|미해당\s*시\s*삭제|해당\s*시)[^)]*\)", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _grams(s: str) -> set[str]:
    s = norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)} or ({s} if s else set())


# ── 명세 ──────────────────────────────────────────────────────────────

def load_spec(form_dir: str) -> dict | None:
    """사람이 쓴 명세. 옛 모양(table 하나)을 새 모양(tables 목록)으로 바꿔 돌려준다."""
    p = os.path.join(form_dir, "overview_fill.yaml")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    if "table" in spec and "tables" not in spec:
        t = spec["table"]
        if t.get("budget"):
            t["budgets"] = [t["budget"]]
        spec["tables"] = [t]
    spec.setdefault("front_keep", list(range(int(spec.get("front_paragraphs", 0)))))
    spec.setdefault("clear_unfilled", "all")
    spec["source"] = "manual"
    return spec


def resolve_spec(form_dir: str, template: str) -> dict | None:
    spec = load_spec(form_dir) or derive_spec(template)
    if spec:
        annotate(spec, template)
    return spec


def annotate(spec: dict, template: str) -> None:
    """머리글 행의 글자를 명세에 싣는다 — 원고 표 머리글을 맞춰 보는 데 쓴다."""
    with zipfile.ZipFile(template) as z:
        root = etree.fromstring(z.read("Contents/section0.xml"))
    tops = [p for p in root if p.tag == q("p")]
    for t in spec["tables"]:
        tbl = next(tops[int(t["paragraph"])].iter(q("tbl")))
        cells = _tbl_cells(tbl)
        for b in t.get("budgets") or []:
            b["names"] = [norm(v["text"]) for k, v in cells.items() if k[0] == int(b["header_row"])]


def _header_maps(hdr: str):
    shaded, chars = set(), {}
    for m in re.finditer(r'<hh:borderFill id="(\d+)".*?</hh:borderFill>', hdr, re.S):
        fc = re.search(r'faceColor="([^"]+)"', m.group(0))
        if fc and fc.group(1).lower() not in ("none", "#ffffff"):
            shaded.add(m.group(1))
    for m in re.finditer(r'<hh:charPr id="(\d+)"([^>]*)>(.*?)</hh:charPr>', hdr, re.S):
        a = m.group(2)
        chars[m.group(1)] = {
            "height": int(re.search(r'height="(\d+)"', a).group(1)),
            "color": re.search(r'textColor="([^"]+)"', a).group(1).upper(),
            "bold": "<hh:bold" in m.group(3),
            "italic": "<hh:italic" in m.group(3),
            "under": 'underline type="NONE"' not in m.group(3),
            "font": (re.search(r'<hh:fontRef hangul="(\d+)"', m.group(3)) or [None, None])[1],
        }
    return shaded, chars


def _black_twin(chars: dict, cid: str) -> str:
    """같은 크기의 검정·보통 글자모양. 원본이 이미 그렇면 그대로."""
    c = chars.get(str(cid))
    if not c:
        return str(cid)
    plain = lambda x: x["color"] == "#000000" and not x["bold"] and not x["italic"] and not x["under"]  # noqa: E731
    if plain(c):
        return str(cid)
    cands = [k for k, x in chars.items() if x["height"] == c["height"] and plain(x)]
    same_font = [k for k in cands if chars[k]["font"] == c["font"]]
    pick = (same_font or cands)
    return min(pick, key=int) if pick else str(cid)


def _tbl_cells(tbl):
    out = {}
    for tc in tbl.findall("hp:tr/hp:tc", NS):
        a, sp = tc.find("hp:cellAddr", NS), tc.find("hp:cellSpan", NS)
        k = (int(a.get("rowAddr")), int(a.get("colAddr")))
        out[k] = {"tc": tc,
                  "rs": int(sp.get("rowSpan")) if sp is not None else 1,
                  "cs": int(sp.get("colSpan")) if sp is not None else 1,
                  "text": " ".join("".join(x.itertext()).strip()
                                   for x in tc.findall("hp:subList/hp:p", NS)).strip()}
    return out


def derive_spec(template: str) -> dict | None:
    """양식을 읽고 명세를 만든다. 첫머리에 채울 표가 없으면 None."""
    with zipfile.ZipFile(template) as z:
        hdr = z.read("Contents/header.xml").decode("utf-8")
        sec = z.read("Contents/section0.xml")
    shaded, chars = _header_maps(hdr)
    root = etree.fromstring(sec)
    tops = [p for p in root if p.tag == q("p")]

    keep, tables, cover = [], [], None
    colors: set[str] = set()
    for i, p in enumerate(tops[:20]):
        tbl = next((t for t in p.iter(q("tbl"))
                    if not any(a.tag == q("tbl") for a in t.iterancestors())), None)
        text = "".join(p.itertext()).strip()
        if tbl is None:
            if NUM_HEADING.match(text):
                break                       # 본문 시작 — 여기까지가 첫머리
                                            # (실측: strategic-2027 은 0번 문단이 「3. 비전」이다)
            continue                        # ※ 안내·빈 줄은 싣지 않는다
        cells = _tbl_cells(tbl)
        is_sh = {k: v["tc"].get("borderFillIDRef") in shaded for k, v in cells.items()}
        nrow, ncol = int(tbl.get("rowCnt")), int(tbl.get("colCnt"))
        # 작성 요령 상자는 버린다 — 머리에 그 말이 있거나 작은 표일 때만.
        # (실측: concept-paper 의 41×6 과제정보 표는 안쪽 한 칸에 「제출 시 삭제」가 있다)
        if GUIDE_BOX.search(text[:40]) or (nrow <= 3 and GUIDE_BOX.search(text)):
            continue

        # 표지 제목 상자 — 한 줄짜리, 번호 칸이 있다
        if nrow == 1 and len(cells) >= 2 and cover is None:
            nums = [k for k, v in cells.items() if re.fullmatch(r"\d{1,3}", v["text"])]
            if nums:
                others = [k for k in cells if k not in nums]
                title = max(others, key=lambda k: int(cells[k]["tc"].find("hp:cellSz", NS).get("width")))
                cover = {"paragraph": i, "number": {"cell": list(nums[0]), "key": "연번"},
                         "title": {"cell": list(title), "from": None}}
                keep.append(i)
                continue

        fields, budgets = _derive_fields(cells, is_sh, nrow, ncol)
        if len(fields) + len(budgets) >= 3:
            for k, v in cells.items():
                if not is_sh[k]:
                    for r in v["tc"].iter(q("run")):
                        col = chars.get(r.get("charPrIDRef"), {}).get("color")
                        if col and col not in ("#000000", "#FFFFFF"):
                            colors.add(col)
            tables.append({"paragraph": i, "fields": fields, "budgets": budgets})
            keep.append(i)
        elif not tables and nrow <= 3 and len(cells) <= 6:
            keep.append(i)                  # 첫머리 장식 상자(「참고 | 양식(안)」)
            # 큰 표를 장식으로 남기면 안 된다(실측: ketep 의 제출 서류 목록표 14×3)
    if not tables and cover is None:
        return None
    # 표지 제목은 과제명 항목에서
    if cover:
        tkey = next((f["key"] for t in tables for f in t["fields"] if "과제명" in f["key"]), None)
        cover["title"]["from"] = tkey
    return {"source": "auto", "front_keep": keep, "section_heading": None,
            "styles": "auto", "clear_unfilled": "guided",
            "draft_color": sorted(colors), "cover": cover, "tables": tables}


def _derive_fields(cells, is_sh, nrow, ncol):
    lab_cs = Counter(v["cs"] for k, v in cells.items() if k[1] == 0 and is_sh[k] and v["cs"] < ncol)
    lab_cs = lab_cs.most_common(1)[0][0] if lab_cs else None

    def is_label(k):
        v = cells[k]
        if v["cs"] >= ncol:
            return is_sh[k]
        return is_sh[k] or (k[1] == 0 and v["cs"] == lab_cs and bool(v["text"]))

    def row_starts(r):
        return sorted(k for k in cells if k[0] == r)

    fields, budgets, owned = [], [], {}
    r = 0
    while r < nrow:
        starts = row_starts(r)
        # 전폭 제목 행
        if len(starts) == 1 and cells[starts[0]]["cs"] >= ncol:
            k = starts[0]
            nxt = row_starts(r + 1) if r + 1 < nrow else []
            if is_label(k) and len(nxt) == 1 and cells[nxt[0]]["cs"] >= ncol and not is_label(nxt[0]):
                fields.append({"key": clean_label(cells[k]["text"]), "aliases": [],
                               "cells": [list(nxt[0])], "mode": "block"})
                r += 2
                continue
            r += 1
            continue
        # 머리글 행 — 칸이 전부 라벨이고 3개 이상, 다음 행이 같은 자리에 값
        covering = [k for k in cells if k[0] < r < k[0] + cells[k]["rs"]]
        # ★ 다음 행은 음영으로만 본다 — 0열 규칙을 쓰면 「’00-’00 (0+0)」 같은 값 칸이
        #   라벨로 잡혀 머리글 행을 못 찾았다(실측).
        if len(starts) >= 3 and all(is_sh[k] for k in starts) and not covering and r + 1 < nrow:
            nxt = row_starts(r + 1)
            if [c for _, c in nxt] == [c for _, c in starts] and not any(is_sh[k] for k in nxt):
                budgets.append({"header_row": r, "value_row": r + 1})
                r += 2
                continue
        # 라벨이 이끄는 행
        labels = [k for k in cells if is_label(k) and k[0] <= r < k[0] + cells[k]["rs"]
                  and cells[k]["cs"] < ncol]
        if labels:
            owner = max(labels, key=lambda k: k[1] + cells[k]["cs"])
            edge = owner[1] + cells[owner]["cs"]
            vals = [k for k in starts if k[1] >= edge and not is_label(k)]
            if vals:
                owned.setdefault(owner, []).append((r, [c for _, c in vals]))
        r += 1

    for owner, rows in sorted(owned.items()):
        text = cells[owner]["text"]
        key = clean_label(text)
        if not re.search(r"[가-힣A-Za-z]{2,}", key):
            continue                        # 「1」「2」 같은 번호 칸은 라벨이 아니다
        parents = [k for k in cells if is_label(k) and k[1] + cells[k]["cs"] <= owner[1]
                   and k[0] <= owner[0] < k[0] + cells[k]["rs"]]
        aliases = [clean_label(cells[p]["text"]) + " " + key for p in parents]
        f = {"key": key, "aliases": aliases, "example": "예시" in text}
        if len(rows) == 1 and len(rows[0][1]) == 1:
            f.update(mode="lines_in_cell", cells=[[rows[0][0], rows[0][1][0]]])
        elif all(len(cs) == 1 for _, cs in rows):
            f.update(mode="cells", cells=[[rr, cs[0]] for rr, cs in rows])
        else:
            f.update(mode="grid", rows=[rr for rr, _ in rows], cols=rows[0][1])
        fields.append(f)
    return fields, budgets


# ── 원고 → 값 ──────────────────────────────────────────────────────────

def _all_fields(spec):
    return [f for t in spec["tables"] for f in t["fields"]]


def collect(blocks, spec):
    """개요 구간의 블록에서 (필드→줄, 연구비 머리글→값, 경고, 옮기지 못한 블록, 맞춘 수).

    받는 모양:
      · 2열 표  | 구분 | 내용 |   — 구분이 빈 행은 윗 행의 이어지는 줄
      · 머리글이 키인 표  | 연번 | 과제명 |  — 다음 행이 값
      · 머리글이 머리글 행과 맞는 표  | 연구기간 | 주관기관 | … |
      · 「키: 값」 글머리/본문 한 줄
    **양식에 자리가 없는 표·행은 버리지 않고 돌려준다** — 엔진이 개요표 뒤에 싣는다.
    """
    fields = _all_fields(spec)
    alias = {}
    for f in fields:
        for name in [f["key"], *(f.get("aliases") or [])]:
            if norm(name):
                alias[norm(name)] = f["key"]
    cover = spec.get("cover") or {}
    cover_num_key = norm((cover.get("number") or {}).get("key", ""))
    brow = {}
    for t in spec["tables"]:
        for b in t.get("budgets") or []:
            for head, names in (b.get("row_aliases") or {}).items():
                for nm in names:
                    brow[norm(nm)] = norm(head)

    values: dict[str, list[str]] = {}
    budget: dict[str, str] = {}
    warns: list[str] = []
    leftover: list = []
    matched: set[str] = set()

    def resolve(raw_key: str):
        k = norm(raw_key)
        if not k:
            return None
        if cover_num_key and k == cover_num_key:
            return "__연번__"
        if k in brow:
            return ("budget", brow[k])
        if k in alias:
            return alias[k]
        pre = [v for a, v in alias.items() if k.startswith(a) or a.startswith(k)]
        if len(set(pre)) == 1:
            return pre[0]
        # 글자쌍 겹침 — 「연계 수요명(정부)」↔「연계 수요명 정부수요」
        g = _grams(k)
        scored = sorted(((len(g & _grams(a)) / len(g), v) for a, v in alias.items()), reverse=True)
        if scored and scored[0][0] >= 0.8 and (len(scored) == 1 or scored[1][0] < scored[0][0]
                                               or scored[1][1] == scored[0][1]):
            return scored[0][1]
        return None

    def put(raw_key: str, text: str, last: list) -> bool:
        if not norm(raw_key):
            if last[0] is None:
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
            matched.add(key)
        last[0] = key
        return True

    heads_known = {n for t in spec["tables"] for b in (t.get("budgets") or [])
                   for n in (b.get("names") or [])}

    last = [None]
    for b in blocks:
        if b.kind == "table" and b.rows:
            head = [norm(c) for c in b.rows[0]]
            if (any("연구기간" in h for h in head) or (heads_known and sum(h in heads_known for h in head) >= 2)) \
                    and len(b.rows) >= 2:
                for h, v in zip(b.rows[0], b.rows[1]):
                    budget[norm(h)] = v.strip()
                matched.add("__연구비__")
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
                leftover.append(Block("table", rows=[b.rows[0] if has_head else ["구분", "내용"]] + miss,
                                      has_header=True))
        elif b.kind in ("bullet", "body"):
            m = re.match(r"^\s*([^:：]{2,20})\s*[:：]\s*(.+)$", b.text)
            if m and put(m.group(1), m.group(2).strip(), last):
                continue
            # 「아래 표와 같음」 같은 도입 문장은 버린다
        elif b.kind != "heading":
            leftover.append(b)
    return values, budget, warns, leftover, len(matched)


# ── 칸 쓰기 ────────────────────────────────────────────────────────────

# 여러 줄 칸 높이 추정.
# ★ 실렌더로 잰 값이다(2026-09-17). 한글은 원본 칸 높이를 그대로 쓰고 **내용에 맞춰
#   늘려 주지 않았다** — 줄 수 × 1300 으로 낮췄더니 마지막 줄이 테두리에 걸렸다.
#   10pt · 130% 한 줄은 110dpi 렌더에서 약 16.4pt ≈ 1650 HWPUNIT 이었고,
#   칸 너비를 넘는 줄은 두 줄로 접혀서 줄 수도 모자랐다. 그래서 접힘까지 세고
#   반 줄 여유를 둔다. 넉넉한 쪽으로 틀리는 편이 낫다(잘리는 것보다 빈칸이 낫다).
LINE_H = 1700
CELL_PAD = 282 + 850
VALUE_LINE_H = 1300     # 값 칸 한 줄 최소
VALUE_PAD = 500
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
    if not need:
        return
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
            # 원본 한 줄 행이 글자 높이에 딱 맞게(1300) 잡힌 양식이 있다 — 한글에서
            # 편집하면 늘어나지만 파일로는 그대로라 글자가 테두리에 닿았다(실렌더).
            height[k] = max(height[k], vis * VALUE_LINE_H + VALUE_PAD)
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


def _slots(tc):
    """칸 안의 글자 조각을 순서대로 — (요소, 'text'|'tail').

    ★ `<hp:t>` 는 자식(탭·줄바꿈)을 품을 수 있고, 그 뒤 글자는 자식의 tail 에 있다.
      t.text 만 보면 「□ 융합형 …<tab/>□ 단일형」의 뒤 선택지를 못 본다(실측).
    """
    out = []
    for t in tc.iter(q("t")):
        out.append((t, "text"))
        for ch in t:
            out.append((ch, "tail"))
    return out


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def check_option(tc, value: str) -> str | None:
    """「□ 융합형 … □ 단일형」 칸이면 값에 맞는 항목만 ■ 로 표시하고, 남는 설명을 돌려준다.

    칸을 통째로 덮으면 양식의 선택지가 사라진다. 맞는 항목이 없으면 None.
    고르기는 **가장 길게 앞머리가 겹치는** 선택지다 — 앞 네 글자만 보면
    「해당(AI활용)」이 「해당(AI개발)」로 잡혔다(실측).
    """
    slots = _slots(tc)
    get = lambda el, attr: (getattr(el, attr) or "")          # noqa: E731
    whole = "".join(get(el, a) for el, a in slots)
    if "□" not in whole and "■" not in whole:
        return None
    opts = [o.strip() for o in re.findall(r"[□■☑]\s*([^□■☑]+)", whole)]
    body = re.sub(r"^[■☑□]\s*", "", value).strip()
    want = norm(body)
    if not want or not opts:
        return None
    scored = sorted(((_common_prefix(norm(o), want), k) for k, o in enumerate(opts)), reverse=True)
    best, idx = scored[0]
    label = norm(opts[idx])
    # 선택지 이름을 거의 다 담아야 고른 것으로 본다(「해당(AI활용)」 → 해당AI활용 6자 중 6자)
    core = norm(re.sub(r"\(.*$", "", opts[idx])) or label
    if best < min(len(label), max(2, len(core))) or (len(scored) > 1 and scored[1][0] == best):
        return None
    seen = -1
    for el, a in slots:
        txt = get(el, a)
        if not txt:
            continue
        chars = list(txt)
        for k, ch in enumerate(chars):
            if ch in "□■☑":
                seen += 1
                chars[k] = "■" if seen == idx else "□"
        setattr(el, a, "".join(chars))
    # 값에서 선택지 이름을 뺀 나머지는 설명이다
    rest = body
    raw_label = opts[idx]
    if rest.replace(" ", "").startswith(raw_label.replace(" ", "")):
        n, k = 0, 0
        target = raw_label.replace(" ", "")
        while k < len(rest) and n < len(target):
            if rest[k] != " ":
                n += 1
            k += 1
        rest = rest[k:].strip(" ,·-")
    else:
        rest = ""
    return rest


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
    sl = [(el, a) for el, a in _slots(para) if getattr(el, a)]
    for el, a in sl:
        setattr(el, a, re.sub(r"\(\s*\)", "", getattr(el, a)))
    for (e1, a1), (e2, a2) in zip(sl, sl[1:]):
        x, y = getattr(e1, a1) or "", getattr(e2, a2) or ""
        if x.rstrip().endswith("(") and y.lstrip().startswith(")"):
            setattr(e1, a1, x.rstrip()[:-1])
            setattr(e2, a2, y.lstrip()[1:])


def _cells(tbl) -> dict[tuple[int, int], etree._Element]:
    return {k: v["tc"] for k, v in _tbl_cells(tbl).items()}


# ── 조립 ──────────────────────────────────────────────────────────────

def front_paragraphs(template: str, spec: dict, values: dict, budget: dict
                     ) -> tuple[list[str], list[str]]:
    """(최상위 문단 XML 문자열 목록, 경고)."""
    with zipfile.ZipFile(template) as z:
        sec = z.read("Contents/section0.xml")
        hdr = z.read("Contents/header.xml").decode("utf-8")
    parts = zip_surgery.parse_section(sec)
    kids = zip_surgery.extract_children(parts.body)
    keep = list(spec["front_keep"])
    front = {i: kids[i] for i in keep}
    warns: list[str] = []
    _, chars = _header_maps(hdr)
    guided = spec.get("clear_unfilled") == "guided"

    colors = spec.get("draft_color") or []
    colors = [colors] if isinstance(colors, str) else list(colors)
    color = "·".join(colors)
    draft_chars = {k for k, v in chars.items() if v["color"] in {c.upper() for c in colors}}

    def style_for(tc, kind: str) -> dict:
        st = spec["styles"]
        if st != "auto":
            return st[kind]
        p0 = tc.find("hp:subList/hp:p", NS)
        r0 = p0.find(".//hp:run", NS) if p0 is not None else None
        cid = r0.get("charPrIDRef") if r0 is not None else "0"
        return {"para": p0.get("paraPrIDRef"), "char": _black_twin(chars, cid)}

    def is_guided(tc) -> bool:
        txt = "".join(tc.itertext()).strip()
        if any(r.get("charPrIDRef") in draft_chars for r in tc.iter(q("run"))):
            return True
        return txt.startswith("※") or bool(PLACEHOLDER.search(txt))

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
                    r.set("charPrIDRef", _black_twin(chars, "0"))
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

    done = set()
    cov = spec.get("cover")
    if cov:
        def fill_cover(p):
            cells = _cells(next(p.iter(q("tbl"))))
            src = cov["title"].get("from")
            title_lines = (values.get(src) if src else None) or values.get("__제목__") or []
            title = re.sub(r"^\(\s*국문\s*\)\s*", "", title_lines[0]).strip() if title_lines else ""
            if not title:
                warns.append("표지: 과제명이 원고에 없어 제목 칸을 비웠다")
            tc = cells[tuple(cov["title"]["cell"])]
            write_cell(tc, [title], style_for(tc, "title"))
            num = values.get("__연번__")
            if num:
                t = cells[tuple(cov["number"]["cell"])].find(".//hp:t", NS)
                if t is not None:
                    t.text = num[0]
        edit(int(cov["paragraph"]), fill_cover)
        done.add(int(cov["paragraph"]))

    for tspec in spec["tables"]:
        need: dict = {}

        def fill_table(p, tspec=tspec, need=need):
            tbl = next(p.iter(q("tbl")))
            cells = _cells(tbl)

            def put_cell(key, lines, kind="value"):
                tc = cells[key]
                write_cell(tc, lines, style_for(tc, kind))
                if any(x.strip() for x in lines):
                    need[key] = (lines, False)          # 값 칸은 늘리기만 한다

            def clear(key, example=False):
                tc = cells[key]
                if not guided or example or is_guided(tc):
                    write_cell(tc, [""], style_for(tc, "value"))

            for f in tspec["fields"]:
                lines = list(values.get(f["key"]) or [])
                mode = f.get("mode", "cells")
                ex = bool(f.get("example"))
                if mode == "block":
                    key = tuple(f["cells"][0])
                    if lines or not guided or is_guided(cells[key]):
                        body = bullets(lines)
                        tc = cells[key]
                        write_cell(tc, body, style_for(tc, "block"))
                        # ★ 원본 칸 높이는 초안 분량(13줄·58줄)에 맞춰 고정돼 있다.
                        #   그대로 두면 네 줄을 써도 칸이 반 쪽을 차지한다(실렌더).
                        need[key] = (body, True)
                    continue
                if mode == "grid":
                    rows, cols = f["rows"], f["cols"]
                    for i, r in enumerate(rows):
                        if i >= len(lines):
                            for c in cols:
                                if (r, c) in cells:
                                    clear((r, c), ex)
                            continue
                        segs = [x.strip() for x in lines[i].split(" / ")]
                        parts_ = segs if len(segs) == len(cols) else [""] * (len(cols) - 1) + [lines[i]]
                        for c, v in zip(cols, parts_):
                            if (r, c) in cells:
                                put_cell((r, c), [v])
                    if len(lines) > len(rows):
                        warns.append(f"개요 「{f['key']}」: 칸 {len(rows)}줄보다 원고가 "
                                     f"{len(lines)}줄 길어 뒤를 마지막 칸에 붙였다")
                        put_cell((rows[-1], cols[-1]), lines[len(rows) - 1:])
                    continue
                targets = [tuple(c) for c in f["cells"]]
                if not lines:
                    for tgt in targets:
                        clear(tgt, ex)
                elif mode == "lines_in_cell":
                    rest = check_option(cells[targets[0]], lines[0]) if len(lines) == 1 else None
                    if rest is None:
                        put_cell(targets[0], lines)
                    elif rest:
                        tc = cells[targets[0]]
                        sub = tc.find("hp:subList", NS)
                        st = style_for(tc, "value")
                        sub.append(_new_para(sub.find("hp:p", NS), st["para"], st["char"], rest))
                        need[targets[0]] = (["".join(tc.itertext()), rest], False)
                else:
                    for i, tgt in enumerate(targets):
                        chunk = lines[i:] if i == len(targets) - 1 else lines[i:i + 1]
                        if chunk:
                            put_cell(tgt, chunk)
                        else:
                            clear(tgt, ex)
                for c in f.get("clear") or []:
                    clear(tuple(c), True)

            for b in tspec.get("budgets") or []:
                hr, vr = int(b["header_row"]), int(b["value_row"])
                heads = {norm("".join(tc.itertext())): col
                         for (r, col), tc in cells.items() if r == hr}
                got: dict[int, list[tuple[str, str]]] = {}
                for h, v in budget.items():
                    col = heads.get(h) or next((c for k, c in heads.items()
                                                if k.startswith(h) or h.startswith(k)), None)
                    if col is None:
                        # 「공동1」↔「공동기관」 — 앞 두 글자로 맞춘다
                        cands = {c for k, c in heads.items() if len(h) >= 2 and k[:2] == h[:2]}
                        col = cands.pop() if len(cands) == 1 else None
                    if col is None:
                        warns.append(f"연구비 표: 양식에 없는 머리글 「{h}」 — 값 「{v}」를 옮기지 못했다")
                        continue
                    if v:
                        got.setdefault(col, []).append((h, v))
                used = set()
                for col, pairs in got.items():
                    if len(pairs) == 1:
                        text = [pairs[0][1]]
                    else:                           # 공동1·공동2 → 한 칸에 이름과 함께
                        text = [f"({h}) {v}" for h, v in pairs]
                    put_cell((vr, col), text, "budget")
                    used.add(col)
                for (r, col), tc in cells.items():
                    if r == vr and col not in used:
                        clear((r, col), True)
            _fit_rows(tbl, cells, need)

        edit(int(tspec["paragraph"]), fill_table)
        done.add(int(tspec["paragraph"]))

    # 편집하지 않은 첫머리 문단에도 초안 표시색이 있으면 걷어낸다
    for idx in keep:
        if idx not in done and any(f'charPrIDRef="{c}"' in front[idx] for c in draft_chars):
            edit(idx, lambda p: None)
    return [front[i] for i in keep], warns


def describe(spec: dict) -> str:
    """작성자에게 줄 안내 — 원고 개요를 어떤 이름으로 쓰면 칸에 들어가는가."""
    if not spec:
        return "이 양식은 첫머리에 채울 표가 없다 — 개요는 원고 표로 새로 짓는다."
    out = [f"# 양식 첫머리 — {'사람이 쓴 명세' if spec.get('source') == 'manual' else '자동 판정'}", ""]
    if spec.get("cover"):
        src = spec["cover"]["title"].get("from") or "문서 제목(# …)"
        out.append(f"- 표지 제목 칸: 「{src}」 첫 줄(국문)에서 채운다")
    out += ["", "## 원고 개요에 쓸 이름 (`| 구분 | 내용 |` 표의 구분 칸)", ""]
    def first_row(f):
        return (f.get("cells") or [[min(f.get("rows") or [0]), 0]])[0][0]
    for t in spec["tables"]:
        for f in sorted(t["fields"], key=first_row):
            kind = {"block": "여러 줄 (글머리)", "grid": "줄마다 한 칸",
                    "cells": "줄마다 한 칸", "lines_in_cell": "한 칸"}.get(f.get("mode"), "")
            ex = " · 예시 칸" if f.get("example") else ""
            out.append(f"- {f['key']}  — {kind}{ex}")
        for b in t.get("budgets") or []:
            out.append(f"- 머리글 표: | {' | '.join(b.get('names') or [])} |")
    out += ["", "맞지 않는 이름은 개요표 뒤에 원고 표 그대로 실린다. "
            f"자동 판정은 {MIN_MATCH_AUTO}개 이상 맞아야 켜진다."]
    return "\n".join(out)


if __name__ == "__main__":
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="양식 첫머리(표지·개요표) 판정 결과를 보여 준다")
    ap.add_argument("--form", required=True, help="forms/<id> 디렉터리")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from . import profile as _profile
    prof = _profile.load(a.form)
    print(describe(resolve_spec(a.form, prof.template)))
