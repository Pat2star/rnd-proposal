# -*- coding: utf-8 -*-
"""계획서 단계에서 **미뤄 놓은 것처럼 보이는 표현**을 잡는다.

## 왜 필요한가 (2026-09-10 사용자 지시)

「협약 시 확정」·「미확보」 같은 말은 **계획서 단계에서 명확해 보이지 않는다.**
실측(demo-15p): 「협약 시 확정」 7회 · 「미확보」 3회 · 「미확정」 1회.

없는 사실을 지어내라는 뜻이 아니다. **굳이 계획서에 드러낼 필요가 있는가**를 묻는 것이다.
값을 모르면 그 문장 자체를 빼거나, 정하는 **절차·시점**을 쓰는 편이 낫다.

    협약 시 확정                → 1차년도 시험계획서에서 확정  (절차를 쓴다)
    금액은 협약 시 확정          → (문장 삭제)                  (굳이 쓸 필요 없다)
    수입의존도는 미확보          → (문장 삭제)

**영문 과제명**은 별개다. 국문이 있으면 짝이 반드시 있어야 한다 —
「협약 시 확정」으로 비워 두지 않는다.

exit 0 통과 · exit 2 위반.
"""
import argparse
import io
import re
import sys

# 미뤄 놓은 티가 나는 표현
VAGUE = [
    ("협약 시 확정", "정하는 절차·시점을 쓰거나 문장을 뺀다"),
    ("협약시 확정", "동상"),
    ("추후 확정", "동상"),
    ("추후 결정", "동상"),
    ("확정 예정", "동상"),
    ("미확보", "값이 없으면 그 문장을 빼는 편이 낫다"),
    ("미확정", "동상"),
    ("별도 산정", "언제 어떻게 산정하는지 쓰거나 뺀다"),
    ("검토 예정", "동상"),
    ("협의 예정", "동상"),
]

EN_TITLE = re.compile(r"\(영문\)\s*([^|\n]+)")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True, help="조립용 원고(.build.md)")
    ap.add_argument("--max-vague", type=int, default=0,
                    help="허용할 모호 표현 수 (기본 0)")
    a = ap.parse_args()
    s = io.open(a.md, encoding="utf-8").read()
    bad = []

    print("=" * 62)
    print("표현 검사 — 미뤄 놓은 것처럼 보이는가")
    print("=" * 62)

    # ① 영문 과제명
    m = EN_TITLE.search(s)
    if not m:
        print("  영문 과제명   없음                      ★위반")
        bad.append("영문 과제명 없음")
    else:
        en = m.group(1).strip()
        placeholder = any(v in en for v, _ in VAGUE) or not re.search(r"[A-Za-z]{4}", en)
        print(f"  영문 과제명   {en[:46]:<46} {'★위반' if placeholder else 'OK'}")
        if placeholder:
            bad.append("영문 과제명이 자리표시")

    # ② 모호 표현
    total = 0
    for word, hint in VAGUE:
        n = s.count(word)
        if n:
            total += n
            print(f"  {word:<12} {n:>3}회   → {hint}")
    print(f"  {'모호 표현 계':<12} {total:>3}회   (허용 {a.max_vague})")
    if total > a.max_vague:
        bad.append(f"모호 표현 {total}건")

    print()
    if bad:
        print("FAIL — " + " · ".join(bad))
        return 2
    print("PASS — 미뤄 놓은 표현 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
