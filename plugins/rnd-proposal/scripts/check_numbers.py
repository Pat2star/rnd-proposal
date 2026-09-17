# -*- coding: utf-8 -*-
"""본문의 정량값이 **근거팩에 있는 값인가**를 본다.

## 왜 필요한가 — 재현성의 유일한 구멍

3회 실행 실측에서 L6(결론 일치도)이 0.64 에 그친 **유일한 원인**이 이것이다.
세 회차가 **같은 게이트 항목에서 막혀 서로 다르게 풀었다.**

    기술분류 비중   c1 50/30/20 안분 · c2 총액만 · c3 미정

게이트가 「비중 합 100%」를 요구하는데 근거팩에 비중이 없으니
하나는 지어내고 하나는 비우고 하나는 얼버무렸다.

**「지어내지 마라」는 규칙은 있었으나 세는 도구가 없었다.**
`check_wording` 은 「협약 시 확정」류를 잡지만 **그럴듯한 숫자는 못 잡는다.**

## 무엇을 보는가

본문에서 **단위가 붙은 정량값**만 뽑아 근거팩(`_ws/*.md`)에 있는지 대조한다.
단위 없는 수(연차 번호·표 번호·목록 번호)는 보지 않는다 — 출처가 필요 없다.

**계산해서 나온 값은 근거팩에 없을 수 있다.** 그래서 기본은 **보고**이고,
`--strict` 를 주면 exit 2 가 된다. 산출식이 본문에 적혀 있으면 정당하다.
"""
import argparse
import glob
import io
import os
import re
import sys

# 단위가 붙은 정량값만. 단위 없는 수는 출처가 필요 없다.
UNIT = (r"℃|%|kW_?th|kW_?e|kW|MWh_?th|MWh_?e|MWh|GWh|MW|kt|톤|tCO2?|TOE|"
        r"bar|K\b|g/day|RT|억\s?달러|억원|만원|억|조원|시간|h\b|년|개월|주|"
        r"건|대|명|배|쪽|p\b|만\s?대|천원")
NUM = re.compile(r"(\d[\d,]*\.?\d*)\s*(" + UNIT + r")")

# 문서 자신이 만드는 구조값 — 출처가 필요 없다
STRUCTURAL = re.compile(r"^(1|2|3|4|5|6|7|8|9|10|100)$")


# ★ 범위 표기 `7.8~13.0%` 는 **앞 숫자에 단위가 안 붙는다.**
#   그대로 두면 앞 값이 항상 「미출처」로 잡혀 잡음이 된다(실측).
RANGE = re.compile(r"(\d[\d,]*\.?\d*)\s*[~–-]\s*(\d[\d,]*\.?\d*)\s*(" + UNIT + r")")


def values(text):
    """(정규화된 값, 단위) 집합. 범위는 양 끝을 둘 다 등록한다."""
    out = set()
    norm = lambda x: x.replace(",", "").rstrip(".")
    unorm = lambda u: re.sub(r"\s+", "", u)
    for m in RANGE.finditer(text):
        u = unorm(m.group(3))
        out.add((norm(m.group(1)), u))
        out.add((norm(m.group(2)), u))
    for m in NUM.finditer(text):
        out.add((norm(m.group(1)), unorm(m.group(2))))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True, help="조립용 원고(.build.md)")
    ap.add_argument("--pack", required=True, help="근거팩 디렉터리(_ws)")
    ap.add_argument("--strict", action="store_true",
                    help="미출처 수치가 있으면 exit 2 (기본은 보고만)")
    a = ap.parse_args()

    body = io.open(a.md, encoding="utf-8").read()
    pack = ""
    files = sorted(glob.glob(os.path.join(a.pack, "*.md")))
    for f in files:
        pack += io.open(f, encoding="utf-8").read()

    bv = values(body)
    pv = values(pack)
    # ★ 본문은 **단위가 붙은 값**만 본다(잡음 제거).
    #   하지만 대조는 **숫자만**으로 한다 — 근거팭은 같은 값을 다른 형식으로 적는다.
    #   실측: `2036` 은 팭에 `2036-10-13`(만료일)로, `13.0` 은 단위 없이 있었다.
    #   단위까지 맞추면 멀쌜한 값이 전부 「미출처」로 잡혔다.
    pnum = set(re.findall(r"\d[\d,]*\.?\d*", pack))
    pnum = {x.replace(",", "").rstrip(".") for x in pnum}
    missing = sorted(v for v in bv
                     if v[0] not in pnum and not STRUCTURAL.match(v[0]))

    print("=" * 64)
    print("수치 출처 검사 — 본문 값이 근거팩에 있는가")
    print("=" * 64)
    print(f"  근거팩       {len(files)}개 파일 · 값 {len(pv)}종")
    print(f"  본문         값 {len(bv)}종")
    print(f"  미출처       {len(missing)}종  "
          f"{'OK' if not missing else ('★' if a.strict else '검토')}")

    if missing:
        for n, u in missing[:24]:
            # 본문에서 그 값이 처음 나오는 줄을 보여 준다
            m = re.search(r"^.*\b" + re.escape(n) + r"\s*" + re.escape(u) + r".*$",
                          body, re.M)
            ctx = (m.group(0).strip()[:62] + "…") if m else ""
            print(f"     {n} {u:<8} {ctx}")
        if len(missing) > 24:
            print(f"     … 외 {len(missing) - 24}종")

    print()
    if missing and a.strict:
        print("FAIL — 근거팩에 없는 정량값이 있다.")
        print("계산값이면 산출식을 본문에 적고, 아니면 그 값을 빼라.")
        return 2
    if missing:
        print("검토 필요 — 계산값이면 산출식이 본문에 있는지 확인하라.")
        return 0
    print("PASS — 본문 정량값이 전부 근거팩에 있다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
