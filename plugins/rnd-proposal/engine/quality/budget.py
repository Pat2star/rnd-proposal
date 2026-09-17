# -*- coding: utf-8 -*-
"""분량 실측 — 총 쪽수 + **장별 배분**.

    PYTHONPATH=$CLAUDE_PLUGIN_ROOT python -m engine.quality.budget --hwpx <out.hwpx> --form forms/<id> --md <md>
    PYTHONPATH=$CLAUDE_PLUGIN_ROOT python -m engine.quality.budget --hwpx <out.hwpx> --form forms/<id> --md <md> --calibrate

출처 — `rfp-proposal-harness` 의 규율 L(`gate_pages.py`)을 이 저장소의 게이트 체계로
옮긴 것이다. 원 저작자의 판단을 그대로 가져왔다:

    「분량은 추정으로 통과시키지 않는다.」
    총량만 재면 **「총합은 맞는데 3장이 두 배로 부푼」** 상태를 놓친다.

★ 이 저장소가 원본과 다르게 하는 것 — **원단위를 상수로 두지 않는다.**
  원단위는 `profile.yaml` 의 `budget` 블록에 **양식별로** 적고, `--calibrate` 가
  실제 산출물에서 다시 재어 그 블록을 갱신한다.

  ※ 정정(2026-08-19): 통합 검토 초안에서 「이 양식은 800자/쪽이라 원본 1,750자/쪽과
    두 배 넘게 다르다」고 적었는데 **틀렸다.** 실제로 재보니
    raw 437자/쪽 · 산문환산 **874자/쪽**이었고, 원본 기본양식(약 1,000자/쪽)과는
    13% 차이다. 두 배로 보였던 것은 양식 차이가 아니라 **표 12개·그림 5장이 먹은
    지면**이었다. 그래서 아래 calibrate 는 raw 와 산문환산을 **둘 다** 낸다 —
    하나만 내면 이 오해가 그대로 재발한다.

실측 경로
    HWPX ──한컴 COM──→ PageCount + PDF ──PyMuPDF──→ 장 시작쪽 → 장별 점유 쪽수

장별 점유 쪽수의 정의(원본과 동일): 다음 장이 시작하기 전까지 소모한 쪽수
(= 다음 장 시작쪽 − 이 장 시작쪽, 마지막 장은 총쪽수 − 시작쪽 + 1).
합이 총쪽수와 정확히 일치한다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from ..hwpx import profile as profile_mod

# 장 제목 판별 — "1. 필요성(배경)" 같은 최상위 번호 제목
CHAPTER_RE = re.compile(r"^\s*(\d+)\.\s*\S")


def chapter_titles(md_path: str) -> list[str]:
    """원고에서 `# ` 한 수준 제목(장)만 순서대로 뽑는다."""
    out = []
    with open(md_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("# ") and not line.startswith("## "):
                out.append(line[2:].strip())
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def measure(hwpx: str, titles: list[str], pdf_out: str | None = None) -> dict:
    """한컴으로 열어 총 쪽수를 읽고, PDF에서 장 시작쪽을 판독한다.

    한컴이나 PyMuPDF가 없으면 **실패가 아니라 미측정**으로 돌려준다.
    거짓 FAIL을 내지 않는 것이 이 저장소의 규칙이다.
    """
    res = {"pages": None, "starts": {}, "spans": {}, "skipped": None}

    from ..hwpx import hancom_check
    tmp_pdf = pdf_out or os.path.splitext(os.path.abspath(hwpx))[0] + "._budget.pdf"
    try:
        r = hancom_check.check(hwpx, tmp_pdf)
    except Exception as e:                      # noqa: BLE001
        # ★ pywin32 경로가 RPC 오류로 죽는 PC 가 있다(실측 2026-08-26).
        #   같은 순간 PowerShell COM 은 정상이었다 — 폴백을 한 번 더 태운다.
        try:
            r = hancom_check.check_via_powershell(hwpx, tmp_pdf)
        except Exception as e2:                 # noqa: BLE001
            res["skipped"] = f"한컴 COM 호출 실패: {e} / 폴백도 실패: {e2}"
            return res
        if not r.get("opened"):
            res["skipped"] = f"한컴 COM 호출 실패: {e} / 폴백 결과: {r.get('errors')}"
            return res
    if not r.get("opened") or not r.get("pages"):
        res["skipped"] = "한컴이 문서를 열지 못했거나 쪽수를 돌려주지 않았다"
        return res
    res["pages"] = int(r["pages"])

    if not r.get("pdf") or not os.path.exists(r["pdf"]):
        res["skipped"] = "PDF 변환 실패 — 총 쪽수만 유효, 장별 배분은 미측정"
        return res
    try:
        import fitz                              # PyMuPDF
    except ImportError:
        res["skipped"] = "PyMuPDF 없음 — 총 쪽수만 유효, 장별 배분은 미측정"
        return res

    doc = fitz.open(r["pdf"])
    want = {_norm(t): t for t in titles}
    for i, page in enumerate(doc):
        text = page.get_text()
        for line in text.splitlines():
            key = _norm(line)
            if key in want and want[key] not in res["starts"]:
                res["starts"][want[key]] = i + 1
    total = doc.page_count
    doc.close()
    res["pages"] = total

    # 장별 점유 = 다음 장 시작 − 이 장 시작 (마지막은 총쪽수까지)
    ordered = sorted(res["starts"].items(), key=lambda kv: kv[1])
    for n, (title, start) in enumerate(ordered):
        end = ordered[n + 1][1] - 1 if n + 1 < len(ordered) else total
        res["spans"][title] = end - start + 1
    return res


def prose_chars(md_path: str) -> int:
    """산문 자수 — 제목·글머리·평문의 텍스트만. 표·플레이스홀더는 뺀다."""
    from ..hwpx import mdblocks
    with open(md_path, encoding="utf-8") as f:
        blocks = mdblocks.parse(f.read())
    n = 0
    for b in blocks:
        if b.kind in ("heading", "bullet", "body") and b.text:
            n += len(re.sub(r"\s", "", b.text))
    return n


def compare(prof, meas: dict, md_path: str) -> tuple[list[str], list[str]]:
    """profile.budget 과 대조. (오류, 경고)"""
    errs, warns = [], []
    b = prof.budget
    if not b:
        warns.append("profile.yaml 에 budget 블록이 없다 — 분량 대조를 건너뛴다 "
                     "(--calibrate 로 만들 수 있다)")
        return errs, warns
    if meas.get("pages") is None:
        warns.append(f"분량 미측정: {meas.get('skipped')}")
        return errs, warns

    hard = b.get("hard_max")
    total = b.get("total")
    if hard and meas["pages"] > int(hard):
        errs.append(f"총 {meas['pages']}쪽 > 상한 {hard}쪽")
    elif total and meas["pages"] > int(total):
        warns.append(f"총 {meas['pages']}쪽 > 목표 {total}쪽 (상한 이내)")

    want = b.get("chapters") or {}
    if want and meas["spans"]:
        tol = int(b.get("chapter_tolerance", 1))
        # ★ 다중 섹션 양식은 비운 섹션마다 문서 끝에 빈 페이지가 붙는다(실측).
        #   그 쪽이 **마지막 장의 점유 쪽수에 잡혀** 거짓 초과를 낸다.
        #   profile.budget.trailing_blank_pages 로 빼 준다.
        blank = int(b.get("trailing_blank_pages", 0))
        spans = dict(meas["spans"])
        if blank and spans:
            last = max(spans, key=lambda t: meas["starts"][t])
            spans[last] = max(0, spans[last] - blank)
            warns.append(
                f"마지막 장 '{last}'에서 빈 섹션 {blank}쪽을 뺐다. "
                f"★ 그 섹션은 **지우는 게 아니라 채워야 할 수도 있다** — "
                f"양식의 추가 섹션이 별첨 서식인 경우가 있다(실측: 이 양식의 "
                f"section1 은 「참고3 요약본 양식(안)」 96KB 짜리 필수 첨부다). "
                f"profile 의 extra_sections 설명을 확인할 것")
        # ★ 장별 절대 상한 — 양식이 명시한 것은 허용오차를 적용하지 않는다.
        #   실측: 이 양식은 개요에 `※ 2page 분량 제한 준수` 를 본문에 박아 뒀다.
        #   목표(chapters)는 ±tol 이지만 상한(chapter_hard_max)은 넘으면 곧 위반이다.
        hard_ch = b.get("chapter_hard_max") or {}
        for title, got in spans.items():
            key = title.split(".")[0].strip()
            cap = hard_ch.get(key)
            if cap is not None and got > int(cap):
                errs.append(f"{title}: {got}쪽 > 양식 상한 {cap}쪽 (허용오차 없음)")
            exp = want.get(key)
            if exp is None:
                continue
            if abs(got - int(exp)) > tol:
                errs.append(f"{title}: {got}쪽 (목표 {exp}쪽, 허용 ±{tol})")
    return errs, warns


def _counts(md_path: str) -> tuple[int, int]:
    """(표 개수, 그림 플레이스홀더 개수)."""
    from ..hwpx import mdblocks
    with open(md_path, encoding="utf-8") as f:
        blocks = mdblocks.parse(f.read())
    tbl = sum(1 for b in blocks if b.kind in ("table", "table_ref"))
    fig = sum(1 for b in blocks if b.kind == "figure")
    return tbl, fig


def calibrate(prof, meas: dict, md_path: str) -> dict:
    """실측에서 이 양식의 원단위를 되돌려 계산한다.

    ★ **두 값을 같이 낸다.** 하나만 내면 해석이 갈린다.

      raw_chars_per_page   산문자수 ÷ 총쪽수
                           표·그림이 먹은 지면까지 나눈 값이라 문서마다 흔들린다.
      prose_chars_per_page 산문자수 ÷ (총쪽수 − 표·그림 추정 점유)
                           **다른 양식과 비교할 수 있는 값**이다.

      실측(2026-08-19) strategic-2027-dist: raw 437 / prose 약 1,000.
      raw 만 보면 rfp-proposal-harness 기본양식(1,000)의 절반처럼 보이지만,
      표·그림 점유를 빼면 거의 같다. **raw 를 양식 특성으로 오해하면 안 된다.**

    표·그림 점유는 원 하네스의 실측 원단위를 초기값으로 쓴다
    (표 3~4열 0.5쪽 / 그림 1쪽). 이것도 양식별로 다시 재는 게 맞다.
    """
    if meas.get("pages") is None:
        return {}
    chars = prose_chars(md_path)
    n_tbl, n_fig = _counts(md_path)
    tbl_cost = float(prof.budget.get("table_page_cost", 0.5))
    fig_cost = float(prof.budget.get("figure_page_cost", 1.0))
    occupied = n_tbl * tbl_cost + n_fig * fig_cost
    prose_pages = max(1.0, meas["pages"] - occupied)
    return {
        "measured_at": None,          # 호출부가 채운다(난수·시각 금지 원칙)
        "basis": f"{prof.form_id} 실측",
        "raw_chars_per_page": round(chars / meas["pages"]),
        "prose_chars_per_page": round(chars / prose_pages),
        "table_page_cost": tbl_cost,
        "figure_page_cost": fig_cost,
        "counted": {"prose_chars": chars, "tables": n_tbl, "figures": n_fig,
                    "prose_pages_est": round(prose_pages, 1)},
        "total": meas["pages"],
        "chapters": {t.split(".")[0].strip(): n for t, n in meas["spans"].items()},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hwpx", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--md", required=True)
    ap.add_argument("--calibrate", action="store_true",
                    help="실측값으로 원단위를 계산해 출력 (profile 에 옮겨 적을 것)")
    ap.add_argument("--json")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    prof = profile_mod.load(a.form)
    titles = chapter_titles(a.md)
    meas = measure(a.hwpx, titles)

    print(f"총 쪽수     : {meas['pages'] if meas['pages'] is not None else '미측정'}")
    if meas.get("skipped"):
        print(f"  [미측정] {meas['skipped']}")
    for t, n in sorted(meas["spans"].items(), key=lambda kv: meas["starts"][kv[0]]):
        print(f"  p{meas['starts'][t]:>3}  {n}쪽  {t}")

    errs, warns = compare(prof, meas, a.md)
    for w in warns:
        print(f"  [경고] {w}")
    for e in errs:
        print(f"  [오류] {e}", file=sys.stderr)

    if a.calibrate:
        cal = calibrate(prof, meas, a.md)
        print("\n# profile.yaml 의 budget 블록에 옮겨 적을 값 "
              "(★ 양식마다 다시 재야 한다)")
        print(json.dumps(cal, ensure_ascii=False, indent=2))

    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"measured": meas, "errors": errs, "warnings": warns},
                      f, ensure_ascii=False, indent=2)
    return 2 if errs else (1 if warns else 0)


if __name__ == "__main__":
    sys.exit(main())
