# -*- coding: utf-8 -*-
"""양식 HWPX → forms/<id>/ 일체 생성.

    PYTHONPATH=$CLAUDE_PLUGIN_ROOT python -m engine.hwpx.extract_form <양식.hwpx> --out forms/strategic-2027

산출물:
    template.hwpx        원본 복사 (sha256 고정)
    profile.yaml         스타일 ID 매핑표 + 작성 규칙  ← 자동 추출
    profile.override.yaml 사람이 정정한 값 (있으면 보존, 없으면 뼈대 생성)
    prologue_run.xml     첫 hp:run 원문 (secPr + colPr) — 파싱 없이 바이트 보존
    skeleton.md          양식 목차
    guidance.md          작성 지침 (유색 안내문 + 형광펜 + 메모)
    extract_report.md    추론 근거 + 신뢰도 + 사람 확인 질문

**핵심 설계**: profile.yaml은 재추출 시 덮어쓰지만 profile.override.yaml은 건드리지
않는다. profile.py가 항상 deep-merge하므로 사람의 정정이 살아남는다.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
import zipfile
from datetime import date

import yaml

from . import borderfill, header_index, observe, infer_roles
from .consts import HWPUNIT_PER_MM, HWPUNIT_PER_PX96

EXTRACTOR_VERSION = "0.1.0"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _page_geometry(hwpx: str) -> dict:
    from lxml import etree
    from .consts import NS
    with zipfile.ZipFile(hwpx) as z:
        sec = etree.fromstring(z.read("Contents/section0.xml"))
    pp = sec.find(".//hp:pagePr", NS)
    m = pp.find("hp:margin", NS)
    g = lambda k: int(m.get(k))
    w, h = int(pp.get("width")), int(pp.get("height"))
    return {"width": w, "height": h,
            "margin": {k: g(k) for k in
                       ("left", "right", "top", "bottom", "header", "footer")},
            "text_width_computed": w - g("left") - g("right")}


def _build_profile(form_id: str, hwpx: str, hidx, obs, inf) -> dict:
    page = _page_geometry(hwpx)
    page["text_width_observed"] = obs.text_width_observed
    # ★ 실측 우선. 계산값과 2 HWPUNIT 차이가 나는데 원인 미상이고,
    #   다른 양식에서는 차이가 2가 아닐 수 있다.
    page["text_width"] = obs.text_width_observed or page["text_width_computed"]
    page["hwpunit_per_mm"] = HWPUNIT_PER_MM
    page["hwpunit_per_px96"] = HWPUNIT_PER_PX96

    roles = {}
    for key, r in inf.roles.items():
        d = {"para": r.para, "char": r.char, "style": r.style,
             "confidence": r.confidence, "evidence": r.evidence}
        if r.samples:
            d["samples"] = r.samples
        if r.warning:
            d["warning"] = r.warning
        if r.review_question:
            d["review_question"] = r.review_question
        if r.fallback_of:
            d["fallback_of"] = r.fallback_of
        # 파생 정보 (빌더가 lineseg 계산에 쓴다)
        if r.para and r.para in hidx.para_pr:
            pp = hidx.para_pr[r.para]
            d["align"] = pp.align
            d["line_spacing_pct"] = pp.line_spacing_pct
            d["indent_left"] = pp.indent_left
            d["intent"] = pp.intent
        if r.char and r.char in hidx.char_pr:
            cp = hidx.char_pr[r.char]
            d["char_height"] = cp.height
            d["font"] = cp.font_hangul
            d["bold"] = cp.bold
        d.update(r.extra)
        roles[key] = d

    first_tbl = obs.tables[0] if obs.tables else {}
    # ★ 표 사례가 없는 양식에서 특정 id를 기본값으로 박으면 안 된다.
    #   실측: 2번 양식은 borderFill이 1,2뿐인데 "3"을 기본값으로 쓰면
    #   tbl@borderFillIDRef=3 미정의 참조가 생겨 문서가 깨진다.
    tbl_bf = first_tbl.get("border_fill")
    if not tbl_bf or tbl_bf not in hidx.border_fill:
        uniform = [(b.left, bid) for bid, b in hidx.border_fill.items()
                   if b.fill is None and b.left
                   and b.left == b.right == b.top == b.bottom]
        if uniform:
            tbl_bf = sorted(uniform, key=lambda x: int(x[1]))[0][1]
        elif hidx.border_fill:
            tbl_bf = sorted(hidx.border_fill, key=int)[0]
        else:
            tbl_bf = None

    # 양식에 표 사례가 있으면 그걸 배우고, 없으면 **표준 표 스타일**을 기준으로
    # 잡는다 (consts.DEFAULT_TABLE_STYLE). 양식이 그 테두리를 갖고 있지 않으면
    # 조립기가 가진 것 중 가장 가까운 것으로 근사하고 경고를 남긴다.
    from .consts import DEFAULT_TABLE_STYLE as DTS
    has_example = bool(obs.tables)
    im = first_tbl.get("in_margin") if has_example else None
    table = {
        "style_source": "양식의 표 사례에서 학습" if has_example
                        else "표준 기본값 (이 양식에 표 사례 없음)",
        "tbl_border_fill": tbl_bf,
        "cell_spacing": int(first_tbl.get("cell_spacing") or DTS["cell_spacing"]),
        "page_break": first_tbl.get("page_break") or DTS["page_break"],
        "repeat_header": int(first_tbl.get("repeat_header")
                             or DTS["repeat_header"]),
        "width_budget": max((t.get("width") or 0) for t in obs.tables) if has_example
                        else page["text_width"],
        "in_margin": im or dict(DTS["in_margin"]),
        "cell_margin": dict(DTS["cell_margin"]),
        "default_row_height": DTS["default_row_height"],
        "stub_cols": 0,
        "zone_rules": {"outer": DTS["outer"], "inner": DTS["inner"],
                       "header_fill": DTS["header_fill"],
                       "note": ("stub 없는 단순 표 전용. 원본 표는 재현하지 않는다. "
                                "양식에 이 조합이 없으면 가진 것 중 가장 가까운 "
                                "borderFill로 근사한다.")},
        "borderfill_index": borderfill.index_for_profile(hidx),
        "id_range": {"min": min(map(int, hidx.border_fill)),
                     "max": max(map(int, hidx.border_fill))},
    }

    fig_role = inf.roles.get("figure_caption")
    figure = {
        "max_width": page["text_width"],
        "hwpunit_per_px96": HWPUNIT_PER_PX96,
        "respect_png_dpi": False,
        # ★ None을 쓰면 안 된다. 캡션이 스타일 폴백으로 잡히면 extra가 비는데,
        #   그대로 두면 XML에 side="None"이 들어가고 한글이 캡션을 왼쪽에
        #   배치해 그림을 오른쪽으로 밀어낸다(2번 양식에서 실측).
        "caption": {"side": ((fig_role.extra.get("side") if fig_role else None)
                             or "BOTTOM"),
                    "gap": 850,
                    "auto_num_type": ((fig_role.extra.get("auto_num_type")
                                       if fig_role else None) or "PICTURE"),
                    "prefix": "그림 ", "role": "figure_caption"},
    }

    bullets = {bid: {"char": ch} for bid, ch in hidx.bullets.items()}
    forbidden = sorted({cid for cid, c in hidx.char_pr.items() if c.is_colored},
                       key=int)

    max_depth = sum(1 for k in roles if k.startswith("bullet_level_")
                    and roles[k].get("para") and not roles[k].get("fallback_of"))

    return {
        "profile_version": 1,
        "form": {
            "id": form_id,
            "template": "template.hwpx",
            "template_sha256": _sha256(hwpx),
            "extracted_at": date.today().isoformat(),
            "extractor_version": EXTRACTOR_VERSION,
        },
        "page": page,
        "section_prologue": {
            "raw_file": "prologue_run.xml",
            "first_para_attrs": obs.first_para_attrs,
            "note": "secPr은 첫 문단 첫 run 안에 있다. 파싱하지 말고 원문을 그대로 삽입한다.",
        },
        "roles": roles,
        "numbering": {
            "outline_ids": sorted(hidx.numberings),
            "levels": (list(hidx.numberings.values())[0]
                       if hidx.numberings else []),
        },
        "bullets": bullets,
        "table": table,
        "figure": figure,
        "lineseg": {
            "emit": True,
            "baseline": "floor(vertsize*0.85 + 0.5)",
            "spacing": "floor(charPr.height*(line_pct-100)/100 + 0.5)",
            "flags": {"normal": 393216, "with_bullet": 2490368},
            "note": "half-up 반올림. 파이썬 round()는 banker's라 표/그림 앵커에서 틀린다.",
        },
        "id_policy": {
            "para_id_body": "0",
            "para_id_in_table": "2147483648",
            "shape_id_base": 2100000000,
            "instid_base": 1030000000,
            "step": 17,
            "note": "난수 금지. 같은 입력이 같은 바이트를 내야 재현자료로 제출할 수 있다.",
        },
        "writing_rules": {
            "max_bullet_depth": max_depth or 3,
            "bullet_char_in_text": False,
            # 연구계획서는 그림 바로 옆에서 설명하는 게 관행이다.
            # 본문에 "그림 1" 같은 숫자를 박으면 한글 자동채번과 어긋날 수 있다.
            "inline_cross_ref": False,
            "inline_bold": (inf.roles["bold"].extra.get("policy") == "apply"),
            "style": "개조식",
            "forbidden_char_prs": forbidden,
            "strip_from_template": ["markpen", "memo", "fieldBegin"],
        },
    }


# 번호가 붙은 제목 — `1.` / `1-1` / `5-3.` 꼴
_NUMBERED = re.compile(r"^\s*(\d+)\s*(?:\.|-(\d+))")


def _write_skeleton(path, obs, inf):
    """양식 목차.

    ★ 실측 결함(2026-08-26, P-패널 형식 위원이 적발): 예전에는 **추론된
    heading_1/heading_2 의 paraPr 과 일치하는 문단만** 모았다. 그래서 역할 추론이
    놓친 제목은 목차에서 통째로 사라졌고, **게이트 2.1 이 그 절을 한 번도 검사한
    적이 없었다.**

    실측: `strategic-2027-dist` 는 `1.` `1-1`~`1-4` `2-1` `2-2` **7개 제목이
    paraPr 35** 인데 추론은 heading_1=36 / heading_2=36 을 골랐다. 목차 20개 중
    7개가 빠진 채로 「필수 절」 기준선이 만들어졌다.

    그래서 이제 **번호 패턴을 1차 기준**으로 삼는다. 번호 제목은 양식이 스스로
    선언한 목차라 추론보다 신뢰도가 높다. 추론 paraPr 은 번호가 없는 제목을
    보조로 줍는 데만 쓴다.
    """
    h1 = inf.roles.get("heading_1")
    h2 = inf.roles.get("heading_2")
    lines = ["# 양식 목차", "",
             "> 번호가 붙은 제목(`1.` `1-1`)을 1차 기준으로 뽑고,",
             "> 번호 없는 제목은 추론된 제목 역할(paraPr)로 보완한다.",
             "> `rp-form-selector`가 이걸 보고 작성 계획을 세운다.", ""]
    found = 0
    for o in obs.paras:
        if not o.is_body or not o.text:
            continue
        t = o.text.strip()
        m = _NUMBERED.match(t) if len(t) < 90 else None
        if m:
            # `1-1` 처럼 하위 번호가 있으면 2수준, `1.` 이면 1수준
            lines.append(f"### {t}" if m.group(2) else f"## {t}")
            found += 1
        elif h1 and o.para == h1.para:
            lines.append(f"## {t}")
            found += 1
        elif h2 and o.para == h2.para:
            lines.append(f"### {t}")
            found += 1
    if not found:
        lines.append("_(제목 역할 문단을 찾지 못했다. profile.override.yaml 확인 필요)_")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return found


def _write_guidance(path, obs, hidx, inf):
    """양식이 품고 있는 작성 지침을 writer용으로 모은다.

    이게 의외로 큰 가치다 — writer가 "3-1 비전에 무엇을 써야 하는가"를 아는
    유일한 소스다. 유색 안내문 + 형광펜 + 검토 메모 세 가지를 모은다.
    """
    h1, h2 = inf.roles.get("heading_1"), inf.roles.get("heading_2")
    section = None
    colored_by_section: dict[str, list[str]] = {}
    para_section: dict[int, str] = {}
    for o in obs.paras:
        if o.is_body and o.text:
            if h2 and o.para == h2.para:
                section = o.text
            elif h1 and o.para == h1.para:
                section = o.text
        para_section[o.index] = section or "(절 미상)"

    for cid, text, pidx in obs.run_texts:
        cp = hidx.char_pr.get(cid)
        if cp and cp.is_colored:
            colored_by_section.setdefault(
                para_section.get(pidx, "(절 미상)"), []).append(
                f"[{cp.text_color}] {text}")

    L = ["# 양식 작성 지침", "",
         "> 이 양식 파일 안에 남아 있던 안내문·형광펜·검토 메모를 모은 것이다.",
         "> **`rp-writer`는 이 문서를 읽고 각 절에 무엇을 써야 하는지 판단한다.**", ""]

    if colored_by_section:
        L += ["## 색 글씨 안내문 (절별)", ""]
        for sec, items in colored_by_section.items():
            L.append(f"### {sec}")
            L += [f"- {t}" for t in items[:20]]
            L.append("")
    if obs.markpen_texts:
        L += ["## 형광펜 표시 구간", ""] + [f"- {t}" for t in obs.markpen_texts[:30]] + [""]
    if obs.memo_texts:
        L += ["## 검토 메모", ""] + [f"- {t}" for t in obs.memo_texts[:30]] + [""]
    if not (colored_by_section or obs.markpen_texts or obs.memo_texts):
        L.append("_(이 양식에는 안내문/형광펜/메모가 없다.)_")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return (sum(len(v) for v in colored_by_section.values()),
            len(obs.markpen_texts), len(obs.memo_texts))


def _write_report(path, form_id, hidx, obs, inf, bf_check, counts):
    q = [r for r in inf.questions() if r.review_question]
    L = [f"# 양식 추출 리포트 — {form_id}", "",
         f"- 문단 {len(obs.paras)}개, 표 {len(obs.tables)}개",
         f"- paraPr {len(hidx.para_pr)} / charPr {len(hidx.char_pr)} / "
         f"borderFill {len(hidx.border_fill)} (id {min(map(int,hidx.border_fill))}~"
         f"{max(map(int,hidx.border_fill))}) / style {len(hidx.style)}",
         f"- 본문폭: 계산 {_page_geometry_cached['text_width_computed']} / "
         f"**실측 {obs.text_width_observed}** (실측 우선)",
         f"- 목차 항목 {counts['skeleton']}개, 안내문 {counts['colored']}건, "
         f"형광펜 {counts['markpen']}건, 메모 {counts['memo']}건", "",
         "## 역할 매핑", "",
         "| 역할 | paraPr | charPr | style | 신뢰도 | 근거 |",
         "|---|---:|---:|---:|:---:|---|"]
    for key in infer_roles.ROLE_KEYS + ["bold"]:
        r = inf.roles[key]
        L.append(f"| `{key}` | {r.para or '—'} | {r.char or '—'} | {r.style or '—'} "
                 f"| {r.confidence} | {r.evidence[:110]} |")

    L += ["", f"## 확인 질문 {len(q)}개", ""]
    if q:
        L.append("> 답을 `profile.override.yaml`에 적으면 재추출해도 살아남는다.\n")
        for i, r in enumerate(q, 1):
            L.append(f"**Q{i}. {r.review_question}**")
            L.append(f"- 근거: {r.evidence}")
            if r.samples:
                L.append(f"- 예시: {r.samples}")
            L.append("")
    else:
        L.append("_(없음 — 전 역할이 high 신뢰도)_\n")

    L += ["## borderFill 존 규칙 자기검증", "",
          f"> {bf_check['note']}", "",
          "| 표 | 크기 | 규칙 일치 | stub 열 |", "|---|---|---|---|"]
    for t in bf_check["tables"]:
        L.append(f"| {t['table']} | {t['size']} | {t['match']}/{t['total']} "
                 f"({t['rate']}%) | {t['stub_cols'] or '없음'} |")

    L += ["", "## 미배정 ID", "",
          f"- paraPr: {dict(list(inf.unassigned_para.items())[:10])}",
          f"- charPr: {dict(sorted(inf.unassigned_char.items(), key=lambda kv: -kv[1])[:10])}",
          "", "## 경고", ""]
    warns = list(hidx.warnings) + list(inf.warnings)
    warns += [f"{k}: {r.warning}" for k, r in inf.roles.items() if r.warning]
    L += ([f"- {w}" for w in warns] if warns else ["_(없음)_"])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return len(q)


_page_geometry_cached: dict = {}


def extract(hwpx: str, out_dir: str, form_id: str | None = None) -> dict:
    global _page_geometry_cached
    form_id = form_id or os.path.basename(out_dir.rstrip("/\\")) or "form"
    os.makedirs(out_dir, exist_ok=True)

    hidx = header_index.from_hwpx(hwpx)
    obs = observe.from_hwpx(hwpx)
    inf = infer_roles.infer(obs, hidx)
    _page_geometry_cached = _page_geometry(hwpx)

    tmpl = os.path.join(out_dir, "template.hwpx")
    if os.path.abspath(hwpx) != os.path.abspath(tmpl):
        shutil.copy2(hwpx, tmpl)

    if obs.prologue_run_raw:
        with open(os.path.join(out_dir, "prologue_run.xml"), "w",
                  encoding="utf-8") as f:
            f.write(obs.prologue_run_raw)

    prof = _build_profile(form_id, tmpl, hidx, obs, inf)
    with open(os.path.join(out_dir, "profile.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(prof, f, allow_unicode=True, sort_keys=False, width=100)

    ovr = os.path.join(out_dir, "profile.override.yaml")
    if not os.path.exists(ovr):
        with open(ovr, "w", encoding="utf-8") as f:
            f.write("# 사람이 정정한 값. profile.yaml을 재생성해도 이 파일은 살아남고\n"
                    "# profile.py가 항상 deep-merge 한다.\n"
                    "#\n# 예시:\n# roles:\n#   heading_2:\n#     para: '16'\n"
                    "#     char: '10'\n#     confidence: high\n"
                    "#     evidence: 사람 확인 완료\n")

    n_sk = _write_skeleton(os.path.join(out_dir, "skeleton.md"), obs, inf)
    n_col, n_mp, n_memo = _write_guidance(
        os.path.join(out_dir, "guidance.md"), obs, hidx, inf)
    bf_check = borderfill.self_check(hidx, obs.tables)
    n_q = _write_report(os.path.join(out_dir, "extract_report.md"), form_id,
                        hidx, obs, inf, bf_check,
                        {"skeleton": n_sk, "colored": n_col,
                         "markpen": n_mp, "memo": n_memo})

    return {"form_id": form_id, "out": out_dir, "questions": n_q,
            "skeleton_items": n_sk, "guidance": (n_col, n_mp, n_memo),
            "borderfill": bf_check, "roles": inf.roles}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hwpx")
    ap.add_argument("--out", required=True)
    ap.add_argument("--id")
    a = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    r = extract(a.hwpx, a.out, a.id)
    print(f"양식 '{r['form_id']}' 추출 완료 → {r['out']}")
    print(f"  목차 {r['skeleton_items']}항목, "
          f"안내문/형광펜/메모 {r['guidance']}, 확인질문 {r['questions']}개")
    for t in r["borderfill"]["tables"]:
        print(f"  표{t['table']} {t['size']}: 존 규칙 일치 {t['match']}/{t['total']} "
              f"({t['rate']}%), stub 열 {t['stub_cols'] or '없음'}")
    print(f"\n  → {os.path.join(a.out, 'extract_report.md')} 의 확인 질문에 답하고")
    print(f"     {os.path.join(a.out, 'profile.override.yaml')} 에 적으세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
