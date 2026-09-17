# -*- coding: utf-8 -*-
"""header.xml에 부족한 borderFill을 **덧붙인다** (기존 ID는 절대 불변).

왜 필요한가
-----------
표준 표 스타일(머리행 회색 #D6D6D6 + 바깥 0.3mm / 안쪽 0.15mm)을 쓰려면
그 조합의 borderFill이 양식에 있어야 한다. 그런데 어떤 양식은 0.1mm 무채움
두 개밖에 없다(실측: kimm-basic). 그런 양식에서는 근사밖에 못 한다.

참조 규격서(KIMM-DESIGN.md §2.10)가 이 상황의 해법을 명시한다:
    "추가는 <끝번호+1>부터, itemCnt 증가, **기존 ID 불변**"

그래서 이 모듈은 **끝에 덧붙이기만** 한다. 기존 항목은 바이트 하나 건드리지
않으므로, 이미 그 ID를 참조하는 본문·머리말·스타일이 전부 그대로 살아 있다.

⚠️ 이걸 쓰면 header.xml이 원본과 바이트 동일하지 않게 된다.
   검증기 Q1.5는 그 경우 **구조적 불변성**으로 판정을 바꾼다:
     · 원본의 모든 id가 속성까지 동일하게 존재하는가
     · 추가된 id가 전부 원본 최대 id 초과인가
     · itemCnt가 실제 개수와 맞는가
   이건 바이트 동일성보다 약한 게 아니라 **더 유용한** 보증이다.
"""
from __future__ import annotations

import re

BORDERFILL_TMPL = (
    '<hh:borderFill id="{id}" threeD="0" shadow="0" centerLine="NONE" '
    'breakCellSeparateLine="0">'
    '<hh:slash type="NONE" Crooked="0" isCounter="0"/>'
    '<hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
    '<hh:leftBorder type="SOLID" width="{l}" color="#000000"/>'
    '<hh:rightBorder type="SOLID" width="{r}" color="#000000"/>'
    '<hh:topBorder type="SOLID" width="{t}" color="#000000"/>'
    '<hh:bottomBorder type="SOLID" width="{b}" color="#000000"/>'
    '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>'
    '{fill}'
    '</hh:borderFill>')

FILL_TMPL = ('<hc:fillBrush><hc:winBrush faceColor="{c}" '
             'hatchColor="#FF000000" alpha="0"/></hc:fillBrush>')


def _fill_xml(color):
    return FILL_TMPL.format(c=color) if color else ""


def plan_additions(hidx, specs: list[dict]) -> list[dict]:
    """이미 있는 조합은 빼고, 정말 없는 것만 추린다."""
    have = set()
    for b in hidx.border_fill.values():
        have.add((b.left, b.right, b.top, b.bottom, b.fill))
    out, seen = [], set()
    for s in specs:
        key = (s["l"], s["r"], s["t"], s["b"], s.get("fill"))
        if key in have or key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def extend(header_xml: bytes, additions: list[dict]) -> tuple[bytes, dict]:
    """(새 header.xml, {spec_key: 새 id}). additions가 비면 원본 그대로."""
    if not additions:
        return header_xml, {}

    text = header_xml.decode("utf-8")
    m = re.search(r'<hh:borderFills\s+itemCnt="(\d+)"\s*>', text)
    if not m:
        raise ValueError("header.xml에서 <hh:borderFills itemCnt=...>를 찾지 못했다")

    ids = [int(x) for x in re.findall(r'<hh:borderFill id="(\d+)"', text)]
    next_id = (max(ids) + 1) if ids else 1

    close = text.find("</hh:borderFills>", m.end())
    if close < 0:
        raise ValueError("</hh:borderFills>를 찾지 못했다")

    chunks, mapping = [], {}
    for s in additions:
        bid = str(next_id)
        chunks.append(BORDERFILL_TMPL.format(
            id=bid, l=s["l"], r=s["r"], t=s["t"], b=s["b"],
            fill=_fill_xml(s.get("fill"))))
        mapping[(s["l"], s["r"], s["t"], s["b"], s.get("fill"))] = bid
        next_id += 1

    new_cnt = int(m.group(1)) + len(additions)
    text = (text[:m.start()]
            + f'<hh:borderFills itemCnt="{new_cnt}">'
            + text[m.end():close]
            + "".join(chunks)
            + text[close:])
    return text.encode("utf-8"), mapping


# 목록형 컨테이너 — id 로 식별되는 항목들. 덧붙이기는 이 안에서만 허용한다.
GROUPS = [("borderFills", "borderFill"), ("charProperties", "charPr"),
          ("tabProperties", "tabPr"), ("numberings", "numbering"),
          ("bullets", "bullet"), ("paraProperties", "paraPr"),
          ("styles", "style"), ("memoProperties", "memoPr")]


def _item_re(item: str, id_pat: str = r"\d+") -> re.Pattern:
    # 자기닫힘(<hh:style …/>)과 여닫이(<hh:paraPr …>…</hh:paraPr>) 둘 다
    return re.compile(
        rf'<hh:{item} id="({id_pat})"(?:[^>]*?/>|[^>]*?>.*?</hh:{item}>)', re.S)


def _entries(text: str, item: str) -> dict[str, str]:
    return {m.group(1): m.group(0) for m in _item_re(item).finditer(text)}


def verify_ids_unchanged(orig_xml: bytes, new_xml: bytes) -> list[str]:
    """기존 항목이 한 글자도 안 바뀌었는지, 추가분이 전부 뒤 번호인지 확인한다.

    ★ 2026-09-17 강화. 전에는 **borderFill 만** 비교했다. 그래서 기존 문단모양의
      줄간격을 180→150 으로 직접 고쳐도 [] 를 돌려주었다(오염 시험으로 확인).
      절대원칙 1(header.xml 불변)이 이 저장소의 핵심 주장인데 재는 범위가
      주장보다 좁았다.

    판정은 가장 강한 형태로 한다 — **추가된 항목을 걷어내고 itemCnt 를 되돌리면
    원본과 바이트가 같아야 한다.** 목록 밖(글꼴·문서 옵션 등)의 변경도 이걸로 잡힌다.
    """
    a_txt, b_txt = orig_xml.decode("utf-8"), new_xml.decode("utf-8")
    errs: list[str] = []
    stripped = b_txt
    for cont, item in GROUPS:
        a, b = _entries(a_txt, item), _entries(b_txt, item)
        for iid, xml in a.items():
            if iid not in b:
                errs.append(f"원본 {item} {iid}가 사라졌다")
            elif b[iid] != xml:
                errs.append(f"원본 {item} {iid}가 변경됐다")
        added = [iid for iid in b if iid not in a]
        if a and added:
            mx = max(map(int, a))
            for iid in added:
                if int(iid) <= mx:
                    errs.append(f"추가된 {item} {iid}가 기존 최대 id({mx}) 이하다")
        # 추가분을 걷어낸다
        for iid in added:
            stripped = stripped.replace(b[iid], "", 1)
        ma = re.search(rf'<hh:{cont}\s+itemCnt="(\d+)"', a_txt)
        if ma:
            stripped = re.sub(rf'(<hh:{cont}\s+itemCnt=")\d+(")',
                              rf"\g<1>{ma.group(1)}\g<2>", stripped, count=1)
    if not errs and stripped != a_txt:
        errs.append("목록 밖의 header 내용이 바뀌었다(글꼴·문서 옵션 등)")
    return errs


def clone_parapr_spacing(header_xml: bytes, spacing: dict[str, int]
                         ) -> tuple[bytes, dict[str, str]]:
    """문단모양을 **줄간격만 바꾼 복제본**으로 뒤 번호에 덧붙인다.

    기존 항목은 건드리지 않는다 — 본문이 새 id 를 가리키게 하는 것은 호출한 쪽 몫이다.
    spacing = {원본 paraPr id: 새 줄간격(%)} → (새 header, {원본 id: 새 id})

    쓰는 경우는 하나다(2026-09-17 사용자 규칙): **공고문·작성요령이 본문 줄간격을
    문구로 정했을 때.** 규정이 없으면 양식 값을 그대로 둔다.
    """
    text = header_xml.decode("utf-8")
    items = _entries(text, "paraPr")
    nxt = max(map(int, items)) + 1
    mapping: dict[str, str] = {}
    clones: list[str] = []
    for oid, pct in spacing.items():
        if oid not in items:
            raise ValueError(f"paraPr {oid} 가 header 에 없다")
        xml = items[oid]
        new = re.sub(r'^<hh:paraPr id="\d+"', f'<hh:paraPr id="{nxt}"', xml)
        new, n = re.subn(r'(<hh:lineSpacing type="PERCENT" value=")\d+(")',
                         rf"\g<1>{int(pct)}\g<2>", new)
        if not n:
            raise ValueError(f"paraPr {oid} 의 줄간격이 PERCENT 형식이 아니다")
        clones.append(new)
        mapping[oid] = str(nxt)
        nxt += 1
    m = re.search(r'<hh:paraProperties\s+itemCnt="(\d+)"\s*>', text)
    close = text.find("</hh:paraProperties>", m.end())
    cnt = int(m.group(1)) + len(clones)
    text = (text[:m.start()] + f'<hh:paraProperties itemCnt="{cnt}">'
            + text[m.end():close] + "".join(clones) + text[close:])
    return text.encode("utf-8"), mapping
