# -*- coding: utf-8 -*-
"""판 간 회귀 검사 — 개정이 직전 판을 되돌리지 않았는가.

    PYTHONPATH=$CLAUDE_PLUGIN_ROOT python -m engine.quality.regress --prev v3.md --curr v4.md
    PYTHONPATH=$CLAUDE_PLUGIN_ROOT python -m engine.quality.regress --prev v3.md --curr v4.md --resolved resolved.txt

출처 — `rfp-proposal-harness` 의 규율 H(`gate_regress.py`). 원 저작자의 실측:

    「개정은 매 라운드 신규 결함을 낳는다 (v2 9건 · v3 4~6건 · v4 4건 · v5 3~5건).
     특히 압축·재작성은 직전 라운드가 「완전 해소 확정」한 항목을 되돌린다.」

이 저장소에는 이 층이 아예 없었다. 게이트가 아무리 촘촘해도 **매번 통과하는 판이
서로 다른 내용을 잃어버리는 것**은 못 잡는다. 평가 패널 루프를 돌리는 순간 필요해진다.

검사
    H-1 필수 문자열 카운트   — 직전 판에 있던 표제·라벨이 사라졌는가
    H-2 수치 토큰 다중집합   — 사라진 수치 전건에 해명을 요구한다
    H-3 그림/표 플레이스홀더 — 선언:사용 1:1 이 깨졌는가
    H-4 「완전 해소 확정」    — 리스트 파일의 문자열이 아직 살아 있는가

★ 이 검사는 **경고를 내는 것이 목적**이다. 줄이는 개정에서는 수치가 사라지는 게
  정상일 수 있다. 그래서 exit 2 는 H-4(명시적으로 확정한 항목이 되돌아간 경우)에만 낸다.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter

# 수치 토큰 — 단위가 붙은 것만 센다. 순수 번호(1., 2-1)는 제외한다.
#
# ★ 실측 결함(2026-08-19): 끝을 `\b` 로 막았더니 한국어에서 거의 발동하지 않았다.
#   ① `1MWth급` — `MWth` 뒤가 `급`(단어문자)이라 `\b` 실패. `MW` 로 짧게 매치해도
#      뒤가 `t` 라 역시 실패 → **본문에 17번 나오는 토큰을 3번으로 세어 거짓 경보**
#   ② `90℃ 열원` — `℃`(비단어) 뒤가 공백(비단어)이라 경계가 아예 없어 **매치 0건**
#   `\b` 대신 「뒤에 영숫자가 오지 않을 것」으로 바꾼다. 한글 조사가 붙는 건 허용한다.
#   긴 단위를 먼저 두어 `MW` 가 `MWth` 를 가로채지 않게 한다.
NUM = re.compile(r"\d[\d,.]*\s?(?:%|℃|°C|MWth|MW|kW|억원|만원|개월|시간|"
                 r"t/h|kg|bar|MPa|배|년|건|명|쪽|K|p)(?![A-Za-z0-9])")
PLACEHOLDER = re.compile(r"\[(FIG|TBL)-(\d+)")
# 표제·라벨 후보 — 굵은 리드와 제목
LABEL = re.compile(r"^#{1,3}\s+(.+)$|^\s*-\s+\*\*(.+?)\*\*", re.M)


def _read(p: str) -> str:
    with open(p, encoding="utf-8") as f:
        return f.read()


def labels(md: str) -> Counter:
    out = Counter()
    for m in LABEL.finditer(md):
        t = (m.group(1) or m.group(2) or "").strip()
        if t:
            out[re.sub(r"\s+", " ", t)] += 1
    return out


def numbers(md: str) -> Counter:
    return Counter(re.sub(r"\s+", "", m.group(0)) for m in NUM.finditer(md))


def placeholders(md: str) -> Counter:
    return Counter(f"{m.group(1)}-{m.group(2)}" for m in PLACEHOLDER.finditer(md))


def compare(prev: str, curr: str, resolved: list[str] | None = None) -> dict:
    res = {"lost_labels": [], "lost_numbers": [], "placeholder_delta": [],
           "resolved_regressed": []}

    lp, lc = labels(prev), labels(curr)
    for k, n in lp.items():
        if lc.get(k, 0) < n:
            res["lost_labels"].append(f"{k} ({n}→{lc.get(k, 0)})")

    np_, nc = numbers(prev), numbers(curr)
    for k, n in np_.items():
        if nc.get(k, 0) < n:
            res["lost_numbers"].append(f"{k} ({n}→{nc.get(k, 0)})")

    pp, pc = placeholders(prev), placeholders(curr)
    for k in sorted(set(pp) | set(pc)):
        if pp.get(k, 0) != pc.get(k, 0):
            res["placeholder_delta"].append(f"{k} ({pp.get(k, 0)}→{pc.get(k, 0)})")

    for line in (resolved or []):
        t = line.strip()
        if t and not t.startswith("#") and t not in curr:
            res["resolved_regressed"].append(t[:60])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prev", required=True, help="직전 판 원고")
    ap.add_argument("--curr", required=True, help="현재 판 원고")
    ap.add_argument("--resolved", help="「완전 해소 확정」 문자열 목록 파일 (한 줄에 하나)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    resolved = []
    if a.resolved and os.path.exists(a.resolved):
        resolved = _read(a.resolved).splitlines()

    r = compare(_read(a.prev), _read(a.curr), resolved)

    def show(title, items, limit=8):
        if not items:
            print(f"  ✅ {title}: 이상 없음")
            return
        print(f"  ⚠ {title}: {len(items)}건")
        for x in items[:limit]:
            print(f"       {x}")
        if len(items) > limit:
            print(f"       … 외 {len(items)-limit}건")

    print(f"판 비교  {os.path.basename(a.prev)} → {os.path.basename(a.curr)}")
    show("H-1 사라진 표제·라벨", r["lost_labels"])
    show("H-2 사라진 수치 토큰", r["lost_numbers"])
    show("H-3 플레이스홀더 증감", r["placeholder_delta"])
    show("H-4 확정 해소 항목 되돌림", r["resolved_regressed"])

    if r["resolved_regressed"]:
        print("\n★ H-4 는 되돌림이다 — 개정 전에 확정한 항목이 사라졌다.", file=sys.stderr)
        return 2
    if r["lost_labels"] or r["lost_numbers"] or r["placeholder_delta"]:
        print("\n※ 줄이는 개정이면 정상일 수 있다. **사라진 전건에 해명을 남길 것.**")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
