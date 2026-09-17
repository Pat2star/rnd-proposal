# -*- coding: utf-8 -*-
"""교정본이 **지우면 안 되는 것을 지웠는지** 본다.

## 왜 필요한가

외부 모델(GPT·Gemini)에게 문장을 다듬게 하면 **수치와 출처가 조용히 사라진다.**
「간결하게」라는 지시를 받은 모델은 `COP 2.5` 를 `높은 효율` 로,
`Energies 18(14) 3806(2025년)` 을 `선행 연구` 로 바꾸는 것을 개선이라 여긴다.

**기존 게이트는 이걸 못 잡는다.** `gate_form` 은 형식을, `gate_pages` 는 분량을 본다.
「원본에 있던 수치가 교정본에 없다」를 보는 검사가 없었다.

## 무엇을 보는가

| 검사 | 왜 |
|---|---|
| **수치 손실** | 정량값이 사라지면 근거정합성 축이 즉시 감점한다 |
| **출처 손실** | 인용이 익명이 되면 「미확인 주장」이 된다 |
| 골격 마커 수 | 리드·슬롯이 바뀌면 골격 게이트 F-11 이 FAIL |
| em-dash | 사용자 요건: 연구계획서에 쓰지 않는다 |
| 연월일 표기 | 사용자 요건: 연도까지만 |

exit 0 통과 · exit 2 위반. 위반이면 **채택하지 않는다.**
"""
import argparse
import io
import re
import sys

# 수치: 단위가 붙었거나 소수점이 있는 것만 — 문단 번호에 걸리지 않게
NUM = re.compile(
    r"\d[\d,]*\.?\d*\s*(?:℃|%|kW|MW|MWh|kWh|GWh|TOE|tCO2?|bar|K|h시간|h|년|억원|만원|배|건|명|쪽|p)"
    r"|\bCOP\s*\d+\.?\d*"
    r"|\d+\.\d+")
SRC = re.compile(r"(?:EP|US|KR|WO|JP)\s?\d[\d\-/]*\s?[A-Z]?\d?"      # 특허번호
                 r"|[A-Z][A-Za-z]+\s+\d+\(\d+\)\s*\d+"               # 저널 권(호) 쪽
                 r"|RS-\d{4}-\d+")                                    # 과제번호
DATE = re.compile(r"20\d{2}[.\-]\d{1,2}[.\-]\d{1,2}|20\d{2}년\s?\d{1,2}월")


def load(p):
    return io.open(p, encoding="utf-8").read()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True, help="원본 원고")
    ap.add_argument("--after", required=True, help="교정본")
    a = ap.parse_args()

    b, c = load(a.before), load(a.after)
    bad = []

    print("=" * 66)
    print("교정본 검사 — 지우면 안 되는 것이 지워졌는가")
    print("=" * 66)

    # ★ 집합만 비교하면 **부분 손실을 놓친다.**
    #   `COP 2.5` 가 6곳에 있다가 3곳이 지워져도 집합 차는 공집합이라
    #   「0건」이 나온다(실측된 거짓 안심).
    #   **완전 소멸은 실패**, 횟수 감소는 보고만 한다 —
    #   중복 정리는 정당한 교정이기 때문이다.
    from collections import Counter
    for label, rx in (("수치", NUM), ("출처", SRC)):
        cb, cc = Counter(rx.findall(b)), Counter(rx.findall(c))
        gone = sorted(k for k in cb if cc[k] == 0)
        fewer = sorted((k, cb[k], cc[k]) for k in cb if 0 < cc[k] < cb[k])
        print(f"  {label} 소멸{'':<6}{len(gone):>4}건  "
              f"{'OK' if not gone else '★손실'}")
        if gone:
            print(f"     사라진 것: {' · '.join(gone[:10])}"
                  + (" …" if len(gone) > 10 else ""))
            bad.append(f"{label} {len(gone)}건 소멸")
        if fewer:
            print(f"  {label} 횟수↓{'':<5}{len(fewer):>4}건  검토")
            print("     " + " · ".join(f"{k} {x}→{y}" for k, x, y in fewer[:6]))

    # ★ 원고에는 □·○ 글자가 없다 — kordoc 이 렌더한다.
    #   마크다운 **목록 층위**로 센다(글자로 세면 항상 0 대 0 이라
    #   검사가 무색무취하게 통과한다).
    LEAD = re.compile(r"^- ", re.M)
    SLOT = re.compile(r"^  - ", re.M)
    for label, rx in (("리드 □", LEAD), ("슬롯 ○", SLOT)):
        nb, nc = len(rx.findall(b)), len(rx.findall(c))
        ok = nb == nc
        print(f"  {label:<10}{nb:>4} → {nc:<4} {'OK' if ok else '★변동'}")
        if not ok:
            bad.append(f"{label} {nb}→{nc}")

    # ★ 구분자를 일괄 치환하면 표의 「해당 없음」 칸까지 바뀐다.
    #   실측(2026-09-09): `| 연계성 | — |` 이 `| 연계성 |: |` 로 깨졌다.
    #   빈 칸처럼 보여 사람이 넘기기 쉽다.
    BROKEN = re.compile(r"\|\s*[:—]\s*\|")
    for label, rx, limit in (("em-dash", re.compile("—"), 0),
                             ("연월일 표기", DATE, 0),
                             ("깨진 표 칸", BROKEN, 0)):
        n = len(rx.findall(c))
        print(f"  {label:<10}{n:>4}건  {'OK' if n <= limit else '★위반'}")
        if n > limit:
            bad.append(f"{label} {n}건")

    print()
    if bad:
        print("FAIL — " + " · ".join(bad))
        print("이 교정본은 채택하지 않는다. 지적된 항목을 되살린 뒤 다시 검사한다.")
        return 2
    print("PASS — 지워진 것 없음. 조립해서 게이트로 넘겨도 된다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
