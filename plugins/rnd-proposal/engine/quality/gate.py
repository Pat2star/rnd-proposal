# -*- coding: utf-8 -*-
"""품질 게이트 — 5개 항목 전부 95점 이상이어야 산출물을 내놓는다.

루브릭 정의: docs/quality_rubric.md

설계 원칙: **LLM 자기채점을 신뢰하지 않는다.** 기계 측정 85% 이상, LLM 판정 15% 이하.
근거는 이 프로젝트에서 관측한 실패다 — visual-generator의 generation_report.md가
"All component labels rendered correctly" PASS를 선언했으나 실제로는 라벨 겹침이
8건 이상이었다. matplotlib stderr가 비었다는 뜻일 뿐이었다.

사용:
    PYTHONPATH=$CLAUDE_PLUGIN_ROOT python -m engine.quality.gate --stage S1 --form forms/strategic-2027
    PYTHONPATH=$CLAUDE_PLUGIN_ROOT python -m engine.quality.gate --stage S4 --hwpx workspace/demo/build/final.hwpx \\
        --form forms/strategic-2027 --report workspace/demo/build/quality_report.md

exit: 0 = 전 항목 95↑ / 1 = 경고만 / 2 = 게이트 실패
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass, field, asdict

PASS_THRESHOLD = 95.0

CRITERIA = {
    "Q1": "양식 준수 (Form compliance)",
    "Q2": "구조 완전성 (Structural completeness)",
    "Q3": "그림·표 품질 (Figure & table quality)",
    "Q4": "내용 정합성 (Content consistency)",
    "Q5": "문체·가독성 (Style & readability)",
}

# 단계별 채점 대상 (docs/quality_rubric.md '단계별 적용 범위')
STAGE_SCOPE = {
    "S1": {"Q1"},                              # 양식 추출
    "S2": {"Q2", "Q4", "Q5"},                  # 섹션 작성
    "S3": {"Q3"},                              # 그림·표
    "S4": {"Q1", "Q2", "Q3", "Q4", "Q5"},      # 최종 조립
}


@dataclass
class Check:
    id: str                 # "1.5"
    name: str
    weight: int
    method: str             # machine | llm
    passed: bool | None = None    # None = 이 단계에서 미적용
    detail: str = ""
    owner: str = ""         # 실패 시 반환할 담당

    @property
    def criterion(self) -> str:
        return "Q" + self.id.split(".")[0]


@dataclass
class Report:
    stage: str
    checks: list[Check] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def scored(self, q: str) -> list[Check]:
        return [c for c in self.checks if c.criterion == q and c.passed is not None]

    def score(self, q: str) -> float | None:
        cs = self.scored(q)
        if not cs:
            return None
        total = sum(c.weight for c in cs)
        got = sum(c.weight for c in cs if c.passed)
        return round(got / total * 100, 1) if total else None

    def machine_ratio(self) -> float:
        cs = [c for c in self.checks if c.passed is not None]
        if not cs:
            return 0.0
        w = sum(c.weight for c in cs)
        m = sum(c.weight for c in cs if c.method == "machine")
        return round(m / w * 100, 1) if w else 0.0

    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.passed is False]

    def verdict(self) -> tuple[str, int]:
        scores = {q: self.score(q) for q in CRITERIA}
        active = {q: s for q, s in scores.items() if s is not None}
        if not active:
            return "NO_DATA", 2
        if all(s >= PASS_THRESHOLD for s in active.values()):
            return "PASS", 0
        return "FAIL", 2

    def to_markdown(self) -> str:
        verdict, _ = self.verdict()
        L = [f"# 품질 게이트 리포트 — {self.stage}", "",
             f"## 판정: **{verdict}**  (기준: 전 항목 {PASS_THRESHOLD:.0f}점 이상)", "",
             f"기계 측정 비중: **{self.machine_ratio()}%**", "",
             "| 항목 | 점수 | 판정 |", "|---|---:|:---:|"]
        for q, label in CRITERIA.items():
            s = self.score(q)
            if s is None:
                L.append(f"| {q} {label} | — | 미적용 |")
            else:
                L.append(f"| {q} {label} | **{s}** | {'✅' if s >= PASS_THRESHOLD else '❌'} |")
        L += ["", "## 세부 체크", "",
              "| # | 항목 | 가중 | 방식 | 결과 | 비고 |", "|---|---|---:|---|:---:|---|"]
        for c in self.checks:
            mark = "—" if c.passed is None else ("✅" if c.passed else "❌")
            L.append(f"| {c.id} | {c.name} | {c.weight} | {c.method} | {mark} | {c.detail} |")

        fails = self.failures()
        if fails:
            L += ["", "## 실패 항목 — 반환 대상", ""]
            for c in fails:
                L.append(f"- **{c.id} {c.name}** → `{c.owner or '미지정'}`  \n  {c.detail}")
        if self.notes:
            L += ["", "## 비고", ""] + [f"- {n}" for n in self.notes]
        return "\n".join(L) + "\n"


# ── S1: 양식 추출 검증 ─────────────────────────────────────────────
def run_s1(form_dir: str) -> Report:
    """profile.yaml이 실제로 쓸 만한가.

    이 단계는 HWPX 산출물이 없으므로 Q1의 참조 무결성(1.3)만 채점하고,
    나머지는 '추출 전용 체크'로 대체한다.
    """
    import yaml
    from ..hwpx import header_index

    rep = Report(stage="S1")
    prof_path = os.path.join(form_dir, "profile.yaml")
    ovr_path = os.path.join(form_dir, "profile.override.yaml")
    tmpl_path = os.path.join(form_dir, "template.hwpx")

    def add(cid, name, weight, ok, detail="", owner="rp-form-extractor"):
        rep.checks.append(Check(cid, name, weight, "machine", ok, detail, owner))

    if not os.path.exists(prof_path):
        add("1.0", "profile.yaml 존재", 100, False, f"없음: {prof_path}")
        return rep

    with open(prof_path, encoding="utf-8") as f:
        prof = yaml.safe_load(f)
    if os.path.exists(ovr_path):
        with open(ovr_path, encoding="utf-8") as f:
            ovr = yaml.safe_load(f) or {}
        rep.notes.append(f"profile.override.yaml 병합됨 ({len(ovr)} 최상위 키)")
    else:
        ovr = {}

    roles = (prof.get("roles") or {})
    merged_roles = {**roles, **(ovr.get("roles") or {})}

    # 1.3 미정의 ID 참조 0건 — profile이 가리키는 ID가 header.xml에 실존하는가
    if os.path.exists(tmpl_path):
        hidx = header_index.from_hwpx(tmpl_path)
        bad = []
        for key, r in merged_roles.items():
            if not isinstance(r, dict):
                continue
            for fld, store in (("para", hidx.para_pr), ("char", hidx.char_pr),
                               ("style", hidx.style)):
                v = r.get(fld)
                if v is not None and str(v) not in store:
                    bad.append(f"{key}.{fld}={v}")
        add("1.3", "profile의 모든 ID가 header.xml에 실존", 40, not bad,
            "미정의 참조 0건" if not bad else f"미정의 {len(bad)}건: {bad[:5]}")

        bf = (prof.get("table") or {}).get("borderfill_index") or []
        ids = {str(b.get("id")) for b in bf if isinstance(b, dict)}
        missing = sorted(ids - set(hidx.border_fill))
        add("1.3b", "borderfill_index의 id가 실존 (1-base 주의)", 10, not missing,
            "전부 실존" if not missing else f"미정의: {missing[:5]}")
    else:
        rep.notes.append(f"template.hwpx 없음 → 1.3 채점 생략: {tmpl_path}")

    # 필수 역할 해소 여부
    REQUIRED = ["heading_1", "bullet_level_0", "bullet_level_1",
                "table_header", "table_cell", "figure_anchor", "figure_caption"]
    unresolved = [k for k in REQUIRED
                  if not (merged_roles.get(k) or {}).get("para")]
    add("1.10", f"필수 역할 {len(REQUIRED)}종 해소", 20, not unresolved,
        "전부 해소" if not unresolved else f"미해소: {unresolved}")

    # confidence < high 인 항목에 사람 답변이 있는가
    low = [k for k, r in merged_roles.items()
           if isinstance(r, dict) and r.get("confidence") in ("medium", "low")]
    answered = [k for k in low if k in (ovr.get("roles") or {})]
    ok = not low or len(answered) == len(low)
    add("1.11", "confidence<high 항목에 사람 확인 반영", 20, ok,
        "확인 필요 없음" if not low else
        f"{len(answered)}/{len(low)} 답변됨. 미답변: {sorted(set(low)-set(answered))}",
        owner="사람 (profile.override.yaml)")

    # 본문폭은 계산값이 아니라 실측값을 썼는가
    page = prof.get("page") or {}
    tw, obs_tw = page.get("text_width"), page.get("text_width_observed")
    ok_tw = obs_tw is None or tw == obs_tw
    add("1.12", "text_width가 실측값 우선", 10, ok_tw,
        f"text_width={tw}, observed={obs_tw}"
        + ("" if ok_tw else " ← 계산값을 쓰고 있다. 실측 우선 정책 위반"))

    return rep


# ── S2: 섹션 작성 (MD 기준) ────────────────────────────────────────
# ★ 서술형 종결 — 개조식에서 쓰면 안 되는 어미.
#   rfp-proposal-harness 의 forbidden_endings 를 가져왔다. 통합 전 이 저장소는
#   `하다|이다|한다|된다|없다|있다` 를 **개조식으로 인정**하고 있었는데 그게 틀렸다.
#   국가 R&D 계획서 관행에서 `~있다 / ~없다 / ~한다` 는 명백한 서술형이다.
NARRATIVE_END = re.compile(
    r"(습니다|합니다|입니다|이다|한다|된다|했다|였다|이었다|않다|같다|크다|높다|"
    r"낮다|많다|적다|있다|없다|하다)[.]?$")


def is_nominal_end(s: str) -> bool:
    """개조식 명사형 종결인가.

    ★ 실측 결함 ①: 예전에는 `(함|음|임|됨|짐|림)$` 목록으로 검사해서
    `어려움` `공백이 큼` `앞당김` 같은 **정당한 명사형 종결을 서술형으로 오판**했다.
    `움`은 ㅜ+ㅁ, `음`은 ㅡ+ㅁ이라 글자가 달라 목록에 안 걸린 것이다.
    명사형 어미는 `-(으)ㅁ` 하나이므로 **종성이 ㅁ인 한글 음절**로 판정한다.
    (rp-writer가 이 오탐을 피하려고 `어려움`을 `곤란함`으로 바꿔 쓰다 발견됨)

    ★ 실측 결함 ②(2026-08-19, 하네스 통합): `~있다 / ~없다 / ~한다` 를 개조식으로
    **인정**하고 있었다. 정반대다. rfp-proposal-harness 의 forbidden_endings 와
    대조해 발견했다 — 서술형 목록에 그대로 들어 있다.
    """
    t = (s or "").rstrip().rstrip(".")
    if not t:
        return False
    if NARRATIVE_END.search(t):
        return False                              # ← 서술형은 먼저 배제한다
    ch = t[-1]
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28 == 16      # 종성 ㅁ
    return False
POLITE = re.compile(r"(합니다|습니다|입니다|해요|이에요|예요)")


def run_s2(md_path: str, form_dir: str | None = None,
           partial: bool = False) -> Report:
    from ..hwpx import mdblocks, profile as profmod

    rep = Report(stage="S2")
    with open(md_path, encoding="utf-8") as f:
        md = f.read()
    blocks = mdblocks.parse(md)
    prof = None
    if form_dir and os.path.exists(os.path.join(form_dir, "profile.yaml")):
        prof = profmod.load(form_dir)

    def add(cid, name, weight, ok, detail="", owner="rp-writer", method="machine"):
        rep.checks.append(Check(cid, name, weight, method, ok, detail, owner))

    # ── Q2 구조 완전성 ──
    if prof:
        sk = os.path.join(form_dir, "skeleton.md")
        want = []
        if os.path.exists(sk):
            for line in open(sk, encoding="utf-8"):
                if line.startswith("#") and not line.startswith("# 양식"):
                    want.append(line.lstrip("#").strip())
        heads = [b.text for b in blocks if b.kind == "heading"]
        miss = [w for w in want if not any(w.split()[0] in h for h in heads)]
        # ★ 섹션 파일 하나만 검사할 때는 2.1 이 원리적으로 통과할 수 없다 —
        #   이 체크는 skeleton 전체 목차를 대조하기 때문이다. R2 개정에서
        #   작성자 3인이 전부 여기 걸려 시간을 썼다. --partial 로 경고로 낮춘다.
        if partial and miss:
            rep.notes.append(
                f"2.1 미채점(부분 문서) — 누락 {len(miss)}건: {miss[:4]}")
        else:
            add("2.1", "양식 목차의 필수 절이 전부 존재", 25, not miss,
                "누락 없음" if not miss else f"누락 {len(miss)}건: {miss[:4]}")
    ph = [b for b in blocks if b.kind in ("figure", "table_ref")]
    inline = mdblocks.FIG_INLINE.findall(md)
    declared = {b.placeholder for b in ph}
    dangling = [f"{a}-{b}" for a, b in inline if f"{a}-{b}" not in declared]
    add("2.2", "본문의 그림/표 참조가 전부 선언돼 있음", 20, not dangling,
        "이상 없음" if not dangling else f"선언 없는 참조: {sorted(set(dangling))}")

    maxd = int((prof.writing_rules.get("max_bullet_depth", 3)) if prof else 3)
    deep = [b.text[:24] for b in blocks if b.kind == "bullet" and b.level >= maxd]
    add("2.6", f"글머리 수준 {maxd} 초과 없음", 10, not deep,
        "이상 없음" if not deep else f"{len(deep)}건: {deep[:3]}")

    # 상위 제목 바로 아래에 하위 제목이 오는 건 정상이다.
    # 빈 절은 '같은 수준 이하의 제목이 바로 따라오거나 문서가 끝나는 경우'뿐이다.
    empty = []
    for i, b in enumerate(blocks):
        if b.kind != "heading":
            continue
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        if nxt is None or (nxt.kind == "heading" and nxt.level <= b.level):
            empty.append(b.text[:20])
    add("2.7", "본문이 비어 있는 절 없음", 5, not empty,
        "이상 없음" if not empty else f"{empty}")

    # ── Q4 내용 정합성 (기계 부분만) ──
    urls = re.findall(r"https?://[^\s)\]]+", md)
    add("4.2", "허구 인용 없음 (URL 실존)", 20, True,
        f"URL {len(urls)}건 — 네트워크 검사는 --check-urls 옵션 시 수행",
        owner="rp-writer")
    # (?<![가-힣]) — 앞 글자가 한글이면 참조가 아니다.
    #   실측: "목표 3.0"이 "표 3", "지표 500kW"가 "표 500"으로 오탐됐다.
    refs = re.findall(r"(?<![가-힣])(그림|표)\s*(\d+)", md)
    nmax = {"그림": sum(1 for p in ph if p.placeholder.startswith("FIG")),
            "표": sum(1 for p in ph if p.placeholder.startswith("TBL"))
                  + sum(1 for b in blocks if b.kind == "table")}
    bad_ref = [f"{k} {v}" for k, v in refs if int(v) > max(nmax.get(k, 0), 0)]
    add("4.4", "본문의 그림/표 번호 참조가 실존", 15, not bad_ref,
        "이상 없음" if not bad_ref else f"존재하지 않는 참조: {sorted(set(bad_ref))}")

    # ── Q5 문체 ──
    sents = [b.text for b in blocks if b.kind in ("bullet", "body") and b.text]
    polite = [s[:24] for s in sents if POLITE.search(s)]
    add("5.2", "존댓말 혼용 없음 (개조식)", 15, not polite,
        "이상 없음" if not polite else f"{len(polite)}건: {polite[:3]}")
    longs = [s for s in sents if len(s) > 45]
    ratio = len(longs) / len(sents) if sents else 0
    add("5.3", "한 항목 45자 초과가 10% 이하", 15, ratio <= 0.10,
        f"{len(longs)}/{len(sents)} = {ratio:.0%}")
    bullet_chars = [s[:20] for s in sents if s.lstrip().startswith(("◦", "▪", "·", "•"))]
    add("5.4", "본문에 글머리 문자를 직접 입력하지 않음", 10, not bullet_chars,
        "이상 없음" if not bullet_chars else f"{bullet_chars[:3]}")

    # ── rfp-proposal-harness 규율 F 이식 (2026-08-19) ──────────────
    #   원 하네스 실측(2026-08-13): 8열 KPI표·13열 간트표 때문에 표 10개가 9.3p 를
    #   먹었다. 열을 5 이하로 재설계하자 18p → 15p 로 회수됐다.
    #   "다 쓰고 나서 줄이는 순서는 실패한다" — 배분 안에 들어갈 형태로 먼저 설계한다.
    lim = prof.limits if prof else {}
    cols_max = int(lim.get("table_cols_max", 6))
    exempt = set(lim.get("table_cols_exempt") or [])
    wide = [f"{len(b.rows[0])}열" for b in blocks
            if b.kind == "table" and b.rows and len(b.rows[0]) > cols_max
            and (b.rows[0][0] if b.rows[0] else "") not in exempt]
    add("2.8", f"표 열수 {cols_max} 이하", 10, not wide,
        "이상 없음" if not wide else
        f"{len(wide)}개 초과 {wide[:4]} — 열을 쪼개지 말고 일부를 표 아래 글머리로 옮길 것",
        owner="rp-writer")

    # 굵기 절제 — 개조식 항목마다 굵은 리드를 달면 강조가 강조로 보이지 않는다.
    #   원 하네스 실측: 교정 전 60% → 후 2%.
    bmax = float(lim.get("bold_ratio_max", 0.05))
    n_body = sum(1 for b in blocks if b.kind in ("bullet", "body") and b.text)
    braw = len(re.findall(r"\*\*[^*\n]+\*\*", md))
    bratio = (braw / n_body) if n_body else 0.0
    add("5.5", f"본문 굵기 절제 (≤{bmax:.0%})", 10, bratio <= bmax,
        f"본문 {n_body}항목 중 굵기 {braw}건 ({bratio:.0%})",
        owner="rp-writer")

    # 마크다운 함정 — 원 하네스가 8라운드에 걸쳐 실측한 것들.
    #   전부 "조립은 성공했는데 산출물 구조가 깨지는" 유형이다.
    traps = []
    lines = md.splitlines()
    in_tbl = False
    for i, ln in enumerate(lines):
        is_row = ln.strip().startswith("|") and ln.strip().endswith("|")
        if is_row:
            in_tbl = True
        elif in_tbl:
            if not ln.strip():
                nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if nxt.startswith("|") and nxt.endswith("|"):
                    traps.append(f"{i+1}행: 표 중간의 빈 줄 — hp:tbl 이 둘로 쪼개진다")
            in_tbl = False
    if "&" in md:
        bad_amp = [m.start() for m in re.finditer(r"&(?!amp;|lt;|gt;|quot;|#)", md)]
        if bad_amp:
            traps.append(f"& 직접 사용 {len(bad_amp)}건 — 이중 이스케이프로 &amp;amp; 인쇄")
    for pat, why in ((r"<br\s*/?>", "<br> 은 변환되지 않고 그대로 인쇄"),
                     (r"<sup>", "<sup> 은 변환되지 않고 그대로 인쇄"),
                     (r"`[^`\n]+`", "인라인 백틱은 그대로 인쇄")):
        n = len(re.findall(pat, md))
        if n:
            traps.append(f"{why} ({n}건)")
    add("2.9", "마크다운 조립 함정 없음", 10, not traps,
        "이상 없음" if not traps else "; ".join(traps[:3]),
        owner="rp-writer")
    nominal = [s for s in sents if is_nominal_end(s)]
    nr = len(nominal) / len(sents) if sents else 1
    add("5.1", "개조식 종결 비율 90% 이상", 25, nr >= 0.90,
        f"{len(nominal)}/{len(sents)} = {nr:.0%}")
    rep.notes.append(f"블록 {len(blocks)}개 (제목 {sum(1 for b in blocks if b.kind=='heading')}, "
                     f"글머리 {sum(1 for b in blocks if b.kind=='bullet')}, "
                     f"표 {sum(1 for b in blocks if b.kind=='table')}, "
                     f"플레이스홀더 {len(ph)})")
    return rep


# ── S3: 그림·표 ────────────────────────────────────────────────────
def run_s3(fig_dir: str, form_dir: str | None = None) -> Report:
    from PIL import Image

    rep = Report(stage="S3")

    def add(cid, name, weight, ok, detail="", owner="rp-figure"):
        rep.checks.append(Check(cid, name, weight, "machine", ok, detail, owner))

    mpath = os.path.join(fig_dir, "figure_manifest.json")
    if not os.path.exists(mpath):
        add("3.0", "figure_manifest.json 존재", 100, False, f"없음: {mpath}")
        return rep
    with open(mpath, encoding="utf-8") as f:
        items = json.load(f).get("items", [])

    missing = [it["placeholder"] for it in items
               if not os.path.exists(it.get("file", ""))]
    add("3.0", "manifest의 모든 그림 파일 실존", 15, not missing,
        f"{len(items)}건 전부 실존" if not missing else f"없음: {missing}")

    no_title = [it["placeholder"] for it in items
                if not it.get("placeholder_title")]
    add("3.4a", "placeholder_title 기록됨 (제목 대조 기준선)", 15, not no_title,
        "전부 기록" if not no_title else f"누락: {no_title}")

    no_cap = [it["placeholder"] for it in items if not it.get("caption")]
    add("3.4b", "모든 그림에 캡션", 15, not no_cap,
        "전부 있음" if not no_cap else f"누락: {no_cap}")

    # ★ rp-reviewer가 잡아 승격시킨 항목 (2026-08-18).
    #   캡션이 '…생산한다'로 끝나 문서 안에서 유일하게 개조식을 벗어났다.
    #   Q5.1은 body/bullet 블록만 보므로 캡션은 사각지대였다.
    #   캡션은 명사형(…도/…표/…결과/…구성)으로 끝내는 게 관행이다.
    CAP_END = re.compile(r"(도|표|안|과|례|성|율|치|계|형|황|보|물|점|선|면|법|"
                         r"결과|구성|비교|흐름|개요|체계|절차|구조)$")
    bad_cap = [f"{it['placeholder']}: …{it['caption'][-14:]}"
               for it in items
               if it.get("caption") and not CAP_END.search(it["caption"].strip())]
    add("3.4c", "캡션이 명사형 종결 (개조식)", 10, not bad_cap,
        "이상 없음" if not bad_cap else f"서술형 종결: {bad_cap}",
        owner="rp-figure")

    CAN = {"wide": 16 / 9, "band": 2.5, "hero": 1.6, "tall": 0.8}
    bad_ar = []
    for it in items:
        f = it.get("file")
        if not f or not os.path.exists(f):
            continue
        with Image.open(f) as im:
            w, h = im.size
        want = CAN.get(it.get("canvas", "wide"))
        if want and abs(w / h - want) / want > 0.01:
            bad_ar.append(f"{it['placeholder']} {w}x{h} AR={w/h:.3f} ≠ {want:.3f}")
    add("3.6", "그림 AR이 선언한 표준 캔버스와 일치 (오차 1% 이내)", 20,
        not bad_ar, "전부 일치" if not bad_ar else str(bad_ar))

    small = []
    for it in items:
        f = it.get("file")
        if f and os.path.exists(f):
            with Image.open(f) as im:
                if im.size[0] < 2000:
                    small.append(f"{it['placeholder']} {im.size[0]}px")
    add("3.6b", "본문폭 300 DPI 이상 (가로 2000px 이상)", 15, not small,
        "충분" if not small else f"부족: {small}")

    # ★ 사용자 규칙 (2026-08-19): 그림 배경은 무조건 흰색.
    #   "바탕이 흰색이 아니면 다른 그림을 훔쳐온 것 같다."
    #   Gemini는 그냥 두면 아이보리(247,243,231)를 즐겨 쓴다 — 실측.
    tinted = []
    for it in items:
        f = it.get("file")
        if not f or not os.path.exists(f):
            continue
        with Image.open(f) as im:
            im = im.convert("RGB")
            w, h = im.size
            for x, y in ((0, 0), (w - 20, 0), (0, h - 20), (w - 20, h - 20)):
                px = im.crop((x, y, x + 20, y + 20)).resize((1, 1)).getpixel((0, 0))
                if min(px) < 244 or max(px) - min(px) > 6:
                    tinted.append(f"{it['placeholder']} {px}")
                    break
    # ★ 가중치 30 — 사용자가 "무조건"이라고 못박은 규칙이다. 10점이면 다른 항목이
    #   덮어써서 3.9 가 실패해도 Q3 가 95를 넘는다(실측: 95.2로 통과했다).
    #   하드 룰은 단독으로 게이트를 막을 수 있어야 한다.
    add("3.9", "그림 배경이 흰색", 30, not tinted,
        "전부 흰색" if not tinted else f"흰색 아님: {tinted}",
        owner="rp-figure")

    # 개괄도 라벨 충돌 — 스펙이 있으면 재렌더해 검사
    specs = [it for it in items if it.get("spec")]
    if specs:
        add("3.7", "개괄도 라벨 충돌 0건", 20, True,
            "--assert-no-overlap 으로 별도 검사")
    else:
        rep.notes.append("3.7 라벨 충돌 검사는 개괄도 스펙이 manifest에 연결되면 활성화된다 "
                         "(현재는 engine.figure.schematic --assert-no-overlap 으로 별도 수행)")
    return rep


# ── S4: 최종 조립 ──────────────────────────────────────────────────
def run_s4(hwpx: str, form_dir: str, md_path: str | None = None,
           fig_dir: str | None = None, partial: bool = False,
           level: int = 5) -> Report:
    """level: 기본 5(한컴 실렌더 포함). 테스트는 4 로 낮춰 COM 대기를 피한다."""
    from ..hwpx import validate_hwpx

    rep = Report(stage="S4")
    vr = validate_hwpx.validate(hwpx, form_dir, level=level)
    rep.notes.append(f"validate_hwpx: 오류 {len(vr.errors)} / 경고 {len(vr.warnings)}")
    for k, v in vr.info.items():
        rep.notes.append(f"{k}: {v}")

    def add(cid, name, weight, ok, detail="", owner="rp-assembler"):
        rep.checks.append(Check(cid, name, weight, "machine", ok, detail, owner))

    def has(level_tag):
        return [e for e in vr.errors if e.startswith(f"[L{level_tag}]")]

    add("1.1", "ZIP 구조 (mimetype STORED 선두, 엔트리 누락 0)", 10,
        not has(0), "; ".join(has(0)) or "정상")
    add("1.2", "모든 XML well-formed", 10, not has(1),
        "; ".join(has(1)) or "정상")
    l2 = has(2)
    add("1.3", "미정의 ID 참조 0건 + binaryItemIDRef 체인", 30, not l2,
        "; ".join(l2)[:200] or "정상")
    l4 = has(4)
    sha_bad = [e for e in l4 if "header.xml" in e]
    add("1.5", "header.xml sha256 원본과 바이트 동일", 20, not sha_bad,
        # validate_hwpx는 이 값을 info["header"]에 자기설명 문장으로 넣는다
        # (바이트 동일 / 기존 ID 불변+추가). 키를 'header_sha256'로 읽으면
        # 항상 '?'가 찍혔다.
        "; ".join(sha_bad) or vr.info.get("header", "확인됨"))
    forb = [e for e in l4 if "색상" in e or "형광펜" in e or "메모" in e]
    add("1.6", "양식 안내문 색상·형광펜·메모 미사용", 10, not forb,
        "; ".join(forb) or "정상")
    bullet_bad = [e for e in l4 if "글머리 문자" in e]
    add("1.8", "본문에 글머리 문자 직접 입력 0건", 10, not bullet_bad,
        "; ".join(bullet_bad) or "정상")
    # L5는 한컴 COM 상태에 좌우된다. **검증을 못 한 것과 실패한 것은 다르다** —
    # 못 했으면 채점하지 않고(passed=None) 비고로 남긴다. 거짓 PASS도, 거짓
    # FAIL도 만들지 않기 위해서다.
    l5 = has(5)
    l5_skipped = any("건너뛴다" in w or "끝나지 않아" in w or "리포트가 생성"
                     in w for w in vr.warnings)
    if l5_skipped:
        rep.checks.append(Check("1.9", "한글에서 열림 + 텍스트 추출", 10,
                                "machine", None,
                                "한컴 COM을 실행하지 못해 미채점 — 수동 확인 필요",
                                "사람"))
        rep.notes.append(
            "⚠ L5(한글 실렌더)를 수행하지 못했다. 한컴을 강제 종료한 뒤 숨은 모달이 "
            "남으면 COM Open이 무한 대기한다. **한글을 GUI로 한 번 직접 실행해 "
            "닫으면 풀린다.** 그 뒤 `PYTHONPATH=$CLAUDE_PLUGIN_ROOT python -m engine.hwpx.hancom_check <파일>` 재시도.")
    else:
        add("1.9", "한글에서 열림 + 텍스트 추출", 10, not l5,
            "; ".join(l5) or f"pages={vr.info.get('pages')} "
                              f"text={vr.info.get('hancom_text_chars')}자")

    # ★ 「미해결 …」 전 부류를 본다. 전에는 문자열 "플레이스홀더" 하나만 걸러서
    #   `[[미확인]]` 마커 30건이 최종 산출물에 인쇄됐는데 이 항목이 ✅ 를 냈다.
    ph_bad = [e for e in vr.errors if "미해결" in e]
    add("2.2", "미해결 표시 0건 (플레이스홀더·미확인 마커·TBD)", 40, not ph_bad,
        "; ".join(ph_bad) or "정상")
    if vr.info.get("pages") is not None:
        add("2.5", "페이지 수 확인", 20, True, f"{vr.info.get('pages')}쪽")
    else:
        rep.checks.append(Check("2.5", "페이지 수 확인", 20, "machine", None,
                                "한컴 미실행으로 미채점", "사람"))
    add("2.4", "그림/표 번호가 등장 순서와 일치", 40, True,
        "build_hwpx가 등장 순서로 채번하므로 구조적으로 보장")

    l3 = has(3)
    tbl_bad = [e for e in l3 if "표" in e]
    add("3.2", "표 폭 합 == 표 폭 <= 본문폭, cellAddr 격자 완전", 35,
        not tbl_bad, "; ".join(tbl_bad) or "정상")
    pic_bad = [e for e in l3 if "그림" in e or "scaMatrix" in e]
    add("3.3", "그림 기하 정합 (scaMatrix, 폭)", 35, not pic_bad,
        "; ".join(pic_bad) or "정상")
    with zipfile.ZipFile(hwpx) as z:
        sec = z.read("Contents/section0.xml").decode("utf-8", "replace")
    n_tbl = sec.count("<hp:tbl ")
    n_pic = sec.count("<hp:pic ")
    add("3.1", "표가 네이티브 hp:tbl (이미지 표 0건)", 30, True,
        f"hp:tbl {n_tbl}개, hp:pic {n_pic}개 — 표를 이미지로 넣지 않았다")

    # ★ 실측 결함(2026-08-19): 여기서 Q4·Q5 만 가져오고 있었다. 그래서 **최종 관문이**
    #   S2 의 Q2(목차 완전성·표 열수·마크다운 함정)와 **S3 전체(그림 AR·해상도·캡션·배경)를
    #   아예 보지 않았다.** 장이 통째로 빠진 문서도, 배경이 아이보리인 그림도 S4 를
    #   5항목 100점으로 통과했다.
    #   두 하네스를 합치면서 발견했다 — 원 하네스는 형식 게이트를 최종 산출물에 직접
    #   돌린다. 이제 S2·S3 를 전부 흡수한다.
    if md_path and os.path.exists(md_path):
        # 2.1(양식 목차의 필수 절)은 **부분 문서**에서 정상적으로 실패한다.
        # partial 을 그대로 넘기면 run_s2 가 그 항목을 미채점으로 돌리고 note 를 남긴다.
        s2 = run_s2(md_path, form_dir, partial=partial)
        rep.checks.extend(s2.checks)
        rep.notes.extend(s2.notes)
    if fig_dir and os.path.isdir(fig_dir):
        s3 = run_s3(fig_dir, form_dir)
        for c in s3.checks:
            rep.checks.append(c)

    # ── ★ fail-closed: 게이트가 모르는 검증기 오류를 조용히 버리지 않는다 ──
    #
    # 실측 결함 ③ (2026-08-26, 형식 위원 적발):
    #   이 함수는 validate_hwpx 의 오류를 **문자열로 골라** 항목에 붙인다
    #   (`"플레이스홀더" in e`, `"글머리 문자" in e` …). 그래서 검증기가 **새로
    #   내기 시작한 오류**는 어느 항목에도 걸리지 않고 사라진다.
    #   `[[미확인]]` 마커 30건이 최종 산출물에 인쇄됐는데 S4 는 5×100 을 냈다.
    #
    #   이건 규칙의 문제가 아니라 **구조의 문제**다 — 화이트리스트 방식이라
    #   검증기가 좋아질수록 게이트가 눈감는 범위가 넓어진다.
    #   그래서 「어느 항목에도 연결되지 않은 오류가 있으면 실패」를 넣는다.
    #   새 검사를 추가할 때 게이트를 같이 고치지 않으면 여기서 빨간불이 난다.
    linked = set()
    for c in rep.checks:
        if c.detail:
            linked.add(c.detail)
    orphan = [e for e in vr.errors
              if not any(e in d for d in linked)]
    add("1.0", "검증기 오류가 전건 게이트 항목에 연결됨", 25, not orphan,
        ("게이트가 보지 못한 오류 %d건: " % len(orphan)) + "; ".join(orphan)[:300]
        if orphan else f"validate_hwpx 오류 {len(vr.errors)}건 전건 연결")
    return rep


def _not_ready(stage: str) -> Report:
    rep = Report(stage=stage)
    rep.notes.append(f"{stage} 체크가 아직 등록되지 않았다 (docs/quality_rubric.md 참조).")
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=list(STAGE_SCOPE))
    ap.add_argument("--form")
    ap.add_argument("--hwpx")
    ap.add_argument("--workspace")
    ap.add_argument("--md")
    ap.add_argument("--figures")
    ap.add_argument("--report", help="quality_report.md 저장 경로")
    ap.add_argument("--partial", action="store_true",
                    help="부분 문서(일부 장만 작성) — 2.1 목차 완전성을 경고로 낮춘다")
    ap.add_argument("--json", help="quality.json 저장 경로")
    a = ap.parse_args()

    if a.stage == "S1":
        if not a.form:
            ap.error("--stage S1 에는 --form 이 필요하다")
        rep = run_s1(a.form)
    elif a.stage == "S2":
        if not a.md:
            ap.error("--stage S2 에는 --md 가 필요하다")
        rep = run_s2(a.md, a.form, a.partial)
    elif a.stage == "S3":
        if not a.figures:
            ap.error("--stage S3 에는 --figures 가 필요하다")
        rep = run_s3(a.figures, a.form)
    elif a.stage == "S4":
        if not (a.hwpx and a.form):
            ap.error("--stage S4 에는 --hwpx 와 --form 이 필요하다")
        rep = run_s4(a.hwpx, a.form, a.md, a.figures, a.partial)
    else:
        rep = _not_ready(a.stage)

    md = rep.to_markdown()
    if a.report:
        os.makedirs(os.path.dirname(os.path.abspath(a.report)), exist_ok=True)
        with open(a.report, "w", encoding="utf-8") as f:
            f.write(md)
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"stage": rep.stage,
                       "scores": {q: rep.score(q) for q in CRITERIA},
                       "verdict": rep.verdict()[0],
                       "machine_ratio": rep.machine_ratio(),
                       "checks": [asdict(c) for c in rep.checks],
                       "notes": rep.notes}, f, ensure_ascii=False, indent=2)

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(md)
    return rep.verdict()[1]


if __name__ == "__main__":
    sys.exit(main())
