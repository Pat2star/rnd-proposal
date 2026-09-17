# -*- coding: utf-8 -*-
"""역할 ↔ ID 추론 — "MD의 `#`을 이 양식에서는 어떤 paraPr/charPr로 쓰나"

**빈도만으로는 안 된다.** 이 양식에서 대제목은 본문에 딱 1번 나오는데 표 안
작성 안내문은 13번 나온다. 그래서 확실한 것부터 소거하는 순서로 간다:

  1. 표 역할      — 구조 신호(cellAddr.rowAddr) → confidence high
  2. 캡션 역할    — 구조 신호(hp:caption 조상 + 부모가 pic/tbl) → high
  3. 그림/표 앵커 — 구조 신호(has_pic/has_tbl) → high
  4. 글머리 수준  — heading.type==BULLET 인 paraPr을 margin.left 오름차순 → high
                    ★ 단 본문에서 쓰인 것만. paraPr 36은 표 안에서만 11회
                      쓰이는데 left=0이라, 필터 없으면 level 0을 차지하고
                      24/25/40이 전부 한 칸씩 밀린다.
  5. 제목 수준    — 복합 신호(글자높이 + 텍스트 정규식 + tabPr + 등장순서) → medium
                    신호 3개 이상 일치하면 high로 승급
  6. body         — 소거법
  7. 미검출       — fallback 체인 + confidence none

모든 역할에 confidence / evidence / samples 를 붙인다. confidence < high 인
항목은 extract_report.md에 사람 확인 질문으로 올라간다.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .header_index import HeaderIndex
from .observe import Observation

H1_PAT = re.compile(r"^\d+\.\s")
H2_PAT = re.compile(r"^(\d+-\d+|\d+\.\d+)\s*")

# MD 계층 → 역할 키. build_hwpx가 이 키로 조회한다.
ROLE_KEYS = [
    "heading_1", "heading_2", "heading_3",
    "bullet_level_0", "bullet_level_1", "bullet_level_2", "bullet_level_3",
    "body", "table_header", "table_cell",
    "figure_anchor", "table_anchor", "figure_caption", "table_caption",
]

FALLBACK_CHAIN = {
    "heading_3": "bullet_level_0",
    "bullet_level_3": "bullet_level_2",
    "table_caption": "figure_caption",
    "table_anchor": "body",
    "figure_anchor": "body",
}


@dataclass
class Role:
    key: str
    para: str | None = None
    char: str | None = None
    style: str | None = None
    confidence: str = "none"           # high | medium | low | none
    evidence: str = ""
    samples: list[str] = field(default_factory=list)
    review_question: str | None = None
    warning: str | None = None
    fallback_of: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        return self.para is not None


@dataclass
class Inference:
    roles: dict[str, Role] = field(default_factory=dict)
    unassigned_para: dict[str, dict] = field(default_factory=dict)
    unassigned_char: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def questions(self) -> list[Role]:
        return [r for r in self.roles.values()
                if r.resolved and r.confidence in ("medium", "low")]


def _mode(counter: Counter, default=None):
    return counter.most_common(1)[0][0] if counter else default


def _black_substitute(hidx: HeaderIndex, char_id: str | None) -> tuple[str | None, str | None]:
    """유색 charPr이면 같은 높이의 검정 charPr로 치환한다.

    이 양식의 표 본문셀 최빈 charPr은 40(#0000FF 8pt)인데, 그건 **양식 작성
    안내문**이지 본문이 아니다. 산출물에 파란 글씨가 섞이면 안 된다.
    """
    if not char_id or char_id not in hidx.char_pr:
        return char_id, None
    cp = hidx.char_pr[char_id]
    if not cp.is_colored:
        return char_id, None
    cands = [cid for cid, c in hidx.char_pr.items()
             if c.height == cp.height and not c.is_colored
             and c.bold == cp.bold and c.font_hangul == cp.font_hangul]
    if not cands:
        cands = [cid for cid, c in hidx.char_pr.items()
                 if c.height == cp.height and not c.is_colored]
    if not cands:
        return char_id, f"유색 charPr {char_id}({cp.text_color})의 검정 대체를 못 찾음"
    sub = sorted(cands, key=int)[0]
    return sub, (f"최빈 charPr {char_id}는 {cp.text_color} 양식 안내문이라 "
                 f"같은 크기 검정 {sub}로 치환함")


# ── 개별 추론 ──────────────────────────────────────────────────────
def _infer_table_roles(obs: Observation, hidx: HeaderIndex, out: dict):
    hdr, cell = Counter(), Counter()
    hdr_tx, cell_tx = [], []
    for o in obs.paras:
        if not o.in_table or o.in_caption or not o.char:
            continue
        key = (o.para, o.char, o.style)
        if o.cell_row == 0:
            hdr[key] += 1
            if o.text and len(hdr_tx) < 3:
                hdr_tx.append(o.text[:24])
        else:
            cell[key] += 1
            if o.text and len(cell_tx) < 3:
                cell_tx.append(o.text[:24])

    if hdr:
        p, c, s = _mode(hdr)
        sub, warn = _black_substitute(hidx, c)
        out["table_header"] = Role(
            "table_header", p, sub, s, "high",
            "표 안 cellAddr.rowAddr==0 문단의 최빈 (paraPr, charPr, style)",
            hdr_tx, warning=warn)
    if cell:
        p, c, s = _mode(cell)
        sub, warn = _black_substitute(hidx, c)
        out["table_cell"] = Role(
            "table_cell", p, sub, s,
            "medium" if warn else "high",
            "표 안 rowAddr!=0 문단의 최빈 조합",
            cell_tx, warning=warn,
            review_question=(
                f"표 본문셀을 paraPr {p} / charPr {sub}로 잡았습니다. {warn} 맞습니까?"
                if warn else None))


def _infer_caption_roles(obs: Observation, out: dict):
    fig, tbl = Counter(), Counter()
    fig_tx, tbl_tx = [], []
    fig_num = tbl_num = None
    for o in obs.paras:
        if not o.in_caption or not o.char:
            continue
        key = (o.para, o.char, o.style)
        if o.caption_owner == "pic":
            fig[key] += 1
            fig_num = fig_num or o.auto_num_type
            if o.text and len(fig_tx) < 3:
                fig_tx.append(o.text[:30])
        elif o.caption_owner == "tbl":
            tbl[key] += 1
            tbl_num = tbl_num or o.auto_num_type
            if o.text and len(tbl_tx) < 3:
                tbl_tx.append(o.text[:30])

    if fig:
        p, c, s = _mode(fig)
        out["figure_caption"] = Role(
            "figure_caption", p, c, s, "high",
            f"hp:pic/hp:caption 내부 문단 (autoNum numType={fig_num})",
            fig_tx, extra={"auto_num_type": fig_num or "PICTURE", "side": "BOTTOM"})
    if tbl:
        p, c, s = _mode(tbl)
        out["table_caption"] = Role(
            "table_caption", p, c, s, "high",
            f"hp:tbl/hp:caption 내부 문단 (autoNum numType={tbl_num})",
            tbl_tx, extra={"auto_num_type": tbl_num or "TABLE", "side": "TOP"})


def _infer_anchor_roles(obs: Observation, out: dict):
    pic, tbl = Counter(), Counter()
    for o in obs.paras:
        if not o.char:
            continue
        if o.has_pic:
            pic[(o.para, o.char, o.style)] += 1
        if o.has_tbl:
            tbl[(o.para, o.char, o.style)] += 1
    if pic:
        p, c, s = _mode(pic)
        out["figure_anchor"] = Role(
            "figure_anchor", p, c, s, "high",
            "hp:pic을 직접 담은 문단 (텍스트 run이 없어 첫 run charPr로 폴백)")
    if tbl:
        p, c, s = _mode(tbl)
        out["table_anchor"] = Role(
            "table_anchor", p, c, s,
            "high" if len(tbl) == 1 else "medium",
            f"hp:tbl을 직접 담은 문단 (관측된 조합 {len(tbl)}종)",
            review_question=(
                f"표 앵커 문단이 {len(tbl)}종 관측됐습니다. paraPr {p}가 맞습니까?"
                if len(tbl) > 1 else None))


def _infer_bullet_levels(obs: Observation, hidx: HeaderIndex, out: dict):
    """★ in_table=False 필터가 필수다. 없으면 전부 한 칸씩 밀린다."""
    usage = obs.usage_by_para()
    all_bullets = hidx.bullet_para_prs()
    if not all_bullets:
        all_bullets = hidx.outline_para_prs()

    body_only = {pid: left for pid, left in all_bullets.items()
                 if usage.get(pid, {}).get("body", 0) > 0}
    excluded = sorted(set(all_bullets) - set(body_only), key=int)

    ordered = sorted(body_only.items(), key=lambda kv: kv[1])
    for lvl, (pid, left) in enumerate(ordered[:4]):
        chars = Counter(o.char for o in obs.paras
                        if o.para == pid and o.is_body and o.char)
        texts = [o.text[:26] for o in obs.paras
                 if o.para == pid and o.is_body and o.text][:3]
        pp = hidx.para_pr[pid]
        bullet_char = hidx.bullets.get(pp.heading_id_ref or "")
        # ★ 글머리도 유색 charPr 치환이 필요하다.
        #   3번 양식(nst-rnd-plan)의 1수준 최빈 charPr 55는 #0000FF 파란
        #   양식 안내문이었다. 표 역할에만 치환을 걸어 뒀더니 그대로 통과해
        #   검증기 L4(forbidden_char_prs)에서 오류가 났다.
        raw_char = _mode(chars)
        sub_char, warn = _black_substitute(hidx, raw_char)
        ev = (f"heading.type={pp.heading_type}, margin.left={left} "
              f"(본문 사용 {usage[pid]['body']}회) → 오름차순 {lvl}번째")
        if excluded:
            ev += f". 본문 미사용 BULLET paraPr {excluded} 제외함"
        out[f"bullet_level_{lvl}"] = Role(
            f"bullet_level_{lvl}", pid, sub_char, None,
            "medium" if warn else "high", ev, texts, warning=warn,
            review_question=(
                f"bullet_level_{lvl}의 최빈 글자모양이 양식 안내문 색이라 "
                f"검정 {sub_char}로 바꿨습니다. 맞습니까?" if warn else None),
            extra={"bullet_char": bullet_char, "indent_left": left,
                   "heading": {"type": pp.heading_type,
                               "id_ref": pp.heading_id_ref,
                               "level": pp.heading_level}})

    if excluded:
        return excluded
    return []


def _infer_heading_levels(obs: Observation, hidx: HeaderIndex, out: dict):
    """복합 신호. 이 양식은 42와 16이 글자높이 1500 동률이라 텍스트 패턴이 결정한다."""
    body_h = None
    if "bullet_level_0" in out and out["bullet_level_0"].char:
        cp = hidx.char_pr.get(out["bullet_level_0"].char)
        body_h = cp.height if cp else None
    body_h = body_h or 1100

    # 글머리 1수준의 들여쓰기가 제목/본문을 가르는 경계다.
    b0 = out.get("bullet_level_0")
    indent_limit = int((b0.extra.get("indent_left") if b0 else None) or 1000)

    cands = {}
    for o in obs.paras:
        if not o.is_body or not o.char or not o.para:
            continue
        # ★ 제목 후보는 **실제 텍스트가 있어야** 한다.
        #   3번 양식(nst-rnd-plan)에서 표 앵커 빈 문단(paraPr 22 / charPr 65,
        #   16pt)이 heading_2로 잡혔다. 대제목(13pt)보다 글자가 커서 위계가
        #   뒤집혔는데, 정작 그 조합으로 쓰인 텍스트는 한 줄도 없었다.
        if not o.text or o.is_anchor:
            continue
        pp = hidx.para_pr.get(o.para)
        cp = hidx.char_pr.get(o.char)
        if not pp or not cp:
            continue
        if pp.heading_type != "NONE":
            continue
        # ★ 들여쓰기 0만 제목으로 보면 안 된다.
        #   3번 양식(nst-rnd-plan)의 2수준 제목 "1) 연구개발 개요"는
        #   paraPr 41(들여쓰기 500)이라 통째로 걸러졌다.
        #   기준은 '글머리 1수준보다 얕게 들어간 것'이다.
        if (pp.indent_left or 0) >= indent_limit:
            continue
        if (cp.height or 0) <= body_h:
            continue
        d = cands.setdefault(o.para, {
            "char": Counter(), "style": Counter(), "texts": [],
            "height": cp.height, "first": o.index, "tab": pp.tab_pr,
            "intent": abs(pp.intent or 0), "h1": 0, "h2": 0, "n": 0})
        d["char"][o.char] += 1
        d["style"][o.style] += 1
        d["n"] += 1
        d["first"] = min(d["first"], o.index)
        if o.text:
            if len(d["texts"]) < 3:
                d["texts"].append(o.text[:26])
            if H1_PAT.match(o.text):
                d["h1"] += 1
            elif H2_PAT.match(o.text):
                d["h2"] += 1

    if not cands:
        return

    def score(item):
        pid, d = item
        # 텍스트 패턴이 가장 강한 신호다.
        pat = -2 if d["h1"] > d["h2"] else (-1 if d["h2"] > d["h1"] else 0)
        return (pat, -(d["height"] or 0), -d["intent"],
                0 if d["tab"] not in (None, "0") else 1, d["first"])

    ranked = sorted(cands.items(), key=score)
    for lvl, (pid, d) in enumerate(ranked[:3], start=1):
        signals = []
        if d["h1"] or d["h2"]:
            signals.append("텍스트패턴")
        heights = {v["height"] for v in cands.values()}
        if len(heights) > 1:
            signals.append("글자높이")
        if d["tab"] not in (None, "0"):
            signals.append("탭설정")
        if len(ranked) > 1:
            signals.append("등장순서")

        conf = "high" if len(signals) >= 3 else ("medium" if signals else "low")
        pat_name = "^N. " if d["h1"] > d["h2"] else ("^N-N " if d["h2"] else "패턴없음")
        ev = (f"heading=NONE, indent=0, 글자높이 {d['height']}(본문 {body_h} 초과), "
              f"텍스트 {pat_name}, tabPr={d['tab']}, 첫등장 #{d['first']}, "
              f"본문 {d['n']}회 — 일치 신호 {len(signals)}개({'/'.join(signals)})")
        q = None
        if conf != "high":
            others = [p for p, _ in ranked if p != pid][:2]
            q = (f"heading_{lvl}을 paraPr {pid} / charPr {_mode(d['char'])}로 "
                 f"잡았습니다. 대안 후보: {others}. 맞습니까?")
        hchar, hwarn = _black_substitute(hidx, _mode(d["char"]))
        if hwarn:
            conf = "medium"
            q = (f"heading_{lvl}의 글자모양이 양식 안내문 색이라 검정 {hchar}로 "
                 f"바꿨습니다. 맞습니까?")
        out[f"heading_{lvl}"] = Role(
            f"heading_{lvl}", pid, hchar, _mode(d["style"]),
            conf, ev, d["texts"], review_question=q, warning=hwarn)


def _infer_body(obs: Observation, hidx: HeaderIndex, out: dict):
    used = {r.para for r in out.values() if r.para}
    c = Counter()
    texts = []
    for o in obs.paras:
        if not o.is_body or not o.char or not o.para or o.is_anchor:
            continue
        if o.para in used:
            continue
        pp = hidx.para_pr.get(o.para)
        if not pp or pp.heading_type != "NONE":
            continue
        if (pp.indent_left or 0) != 0 or (pp.intent or 0) != 0:
            continue
        c[(o.para, o.char, o.style)] += 1
        if o.text and len(texts) < 3:
            texts.append(o.text[:26])
    if c:
        p, ch, s = _mode(c)
        # 예시 텍스트가 하나도 없으면 그 조합은 '빈 문단'만 대표한다 —
        # 평문단 서식으로 신뢰할 근거가 못 된다.
        conf = "medium" if texts else "low"
        q = None
        warn = None
        if not texts:
            warn = ("본문에 텍스트 있는 평문단이 없다(이 양식은 전부 글머리 항목). "
                    "빈 문단 서식을 body로 잡았으니 확인 필요.")
            q = (f"이 양식에는 글머리 없는 평문단 사례가 없습니다. "
                 f"body를 paraPr {p} / charPr {ch}로 잡았는데, "
                 f"bullet_level_0({out.get('bullet_level_0').para if out.get('bullet_level_0') else '?'})를 "
                 f"쓰는 편이 나을까요?")
        out["body"] = Role("body", p, ch, s, conf,
                           "제목/글머리/앵커로 배정되지 않은 평문단 중 최빈 "
                           "(heading=NONE, indent=0, intent=0)", texts,
                           review_question=q, warning=warn)


# ── 스타일 이름 폴백 ───────────────────────────────────────────────
# 한글 양식은 언어와 무관하게 표준 engName을 갖는다:
#   Normal(바탕글) Body(본문) Outline 1..N(개요) Page Number Header Footnote Memo
# 양식에 그 요소의 **사례가 없어도** 스타일 정의는 대개 살아 있다.
# 관측 기반 추론이 실패했을 때만 쓰고, 신뢰도는 low로 두어 사람 확인을 강제한다.
_ENG_FALLBACK = {
    "heading_1": ["Outline 1"],
    "heading_2": ["Outline 2"],
    "heading_3": ["Outline 3"],
    "bullet_level_0": ["Outline 4", "Outline 3", "Body"],
    "bullet_level_1": ["Outline 5", "Outline 4"],
    "bullet_level_2": ["Outline 6", "Outline 5"],
    "body": ["Body", "Normal"],
    "table_header": ["Normal", "Body"],
    "table_cell": ["Normal", "Body"],
    "figure_caption": ["Normal", "Body"],
    # ★ table_caption / table_anchor / figure_anchor 는 일부러 뺐다.
    #   이 셋은 '형제 역할을 따라가는 것'이 표준 스타일 이름보다 낫다.
    #   표 캡션은 그림 캡션과 같은 서식(가운데정렬 130%)이어야지 바탕글이면 안 된다.
    #   FALLBACK_CHAIN이 처리하도록 남겨 둔다.
}

_NO_EXAMPLE_NOTE = {
    "table_header": "이 양식에는 표 사례가 없다",
    "table_cell": "이 양식에는 표 사례가 없다",
    "figure_caption": "이 양식에는 그림 캡션 사례가 없다",
    "table_caption": "이 양식에는 표 캡션 사례가 없다",
}


def _infer_from_style_names(hidx: HeaderIndex, out: dict):
    by_eng = {}
    for sid, s in hidx.style.items():
        if s.eng_name:
            by_eng.setdefault(s.eng_name.strip(), sid)

    for key, engs in _ENG_FALLBACK.items():
        cur = out.get(key)
        if cur is not None and cur.para:
            continue
        for eng in engs:
            sid = by_eng.get(eng)
            if sid is None:
                continue
            st = hidx.style[sid]
            if not st.para_pr or st.para_pr not in hidx.para_pr:
                continue
            note = _NO_EXAMPLE_NOTE.get(key, "본문에 이 역할의 사례가 없다")
            out[key] = Role(
                key, st.para_pr, st.char_pr, sid, "low",
                f"{note}. 표준 스타일 '{st.name}'(engName={eng}, id={sid})의 "
                f"문단모양 {st.para_pr} / 글자모양 {st.char_pr}을 후보로 제안한다",
                review_question=(
                    f"{key}을 표준 스타일 '{st.name}'(paraPr {st.para_pr} / "
                    f"charPr {st.char_pr})로 잡았습니다. {note}라 관측으로는 "
                    f"확인할 수 없었습니다. 맞습니까?"),
                warning=f"{key}: 관측 사례 없음 → 스타일 이름으로 추정")
            break


# ── 메인 ───────────────────────────────────────────────────────────
def infer(obs: Observation, hidx: HeaderIndex) -> Inference:
    out: dict[str, Role] = {}

    _infer_table_roles(obs, hidx, out)
    _infer_caption_roles(obs, out)
    _infer_anchor_roles(obs, out)
    excluded_bullets = _infer_bullet_levels(obs, hidx, out)
    _infer_heading_levels(obs, hidx, out)
    _infer_body(obs, hidx, out)

    _infer_from_style_names(hidx, out)

    inf = Inference(roles=out)

    if excluded_bullets:
        inf.warnings.append(
            f"BULLET paraPr {excluded_bullets}는 본문에서 쓰이지 않아(표 전용) "
            f"글머리 수준 후보에서 제외했다. 이 필터가 없으면 수준이 한 칸씩 밀린다.")

    # fallback 체인
    for key in ROLE_KEYS:
        if key in out:
            continue
        src = FALLBACK_CHAIN.get(key)
        if src and src in out:
            base = out[src]
            out[key] = Role(key, base.para, base.char, base.style, "none",
                            f"양식에 대응 서식이 없어 '{src}' 설정을 전용함",
                            fallback_of=src,
                            warning=f"{key} 미검출 → {src} 폴백")
        else:
            out[key] = Role(key, None, None, None, "none",
                            "양식에서 검출되지 않았고 폴백 대상도 없음",
                            warning=f"{key} 미검출")

    # 인라인 bold: 본문용 bold charPr이 있는지
    body_char = out.get("body").char if out.get("body") else None
    body_h = hidx.char_pr[body_char].height if body_char in hidx.char_pr else None
    bold_cands = [cid for cid, c in hidx.char_pr.items()
                  if c.bold and not c.is_colored and c.height == body_h]
    out["bold"] = Role(
        "bold", None, (sorted(bold_cands, key=int)[0] if bold_cands else None),
        None, "medium" if bold_cands else "none",
        (f"본문 높이({body_h})와 같은 bold charPr {sorted(bold_cands, key=int)[:3]} 발견"
         if bold_cands else
         "본문 높이와 같은 bold charPr이 없다 → v1은 **굵게** 마크업을 제거(strip)"),
        extra={"policy": "apply" if bold_cands else "strip"})

    # ★ OUTLINE 문단모양은 한글이 개요 번호(1. 가. 1)…)를 자동으로 붙인다.
    #   글머리·본문·앵커에 쓰면 텍스트 앞에 원치 않는 번호가 생긴다(2번 양식 실측:
    #   '1. 산업 공정열…', 그림 옆 '1)').
    #   **폴백 체인까지 끝난 뒤에** 검사해야 체인으로 채워진 역할도 잡힌다.
    _OUTLINE_UNSAFE = ("bullet_level_", "body", "figure_anchor", "table_anchor",
                       "figure_caption", "table_caption", "table_cell",
                       "table_header")
    for key, r in out.items():
        if not key.startswith(_OUTLINE_UNSAFE) or not r.para:
            continue
        pp = hidx.para_pr.get(r.para)
        if pp and pp.heading_type == "OUTLINE":
            r.warning = ((r.warning + " / ") if r.warning else "") + (
                f"paraPr {r.para}는 heading=OUTLINE이라 한글이 개요 번호를 "
                f"자동으로 붙인다. BULLET 또는 NONE 문단모양이 안전하다.")
            if r.confidence == "high":
                r.confidence = "medium"
                r.review_question = (
                    f"{key}에 OUTLINE 문단모양 {r.para}를 쓰면 개요 번호가 "
                    f"자동으로 붙습니다. 그래도 이걸 쓰시겠습니까?")

    # 미배정 ID 목록 (리포트용)
    assigned_p = {r.para for r in out.values() if r.para}
    assigned_c = {r.char for r in out.values() if r.char}
    usage = obs.usage_by_para()
    for pid, u in usage.items():
        if pid not in assigned_p and sum(u.values()) > 0:
            inf.unassigned_para[pid] = u
    char_use = Counter(o.char for o in obs.paras if o.char)
    for cid, n in char_use.items():
        if cid not in assigned_c:
            inf.unassigned_char[cid] = n

    return inf
