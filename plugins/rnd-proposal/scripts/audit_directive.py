# -*- coding: utf-8 -*-
"""개정지시서 수록률 감사 — 위원 회수표가 지시서에 전건 실렸는가.

    python $CLAUDE_PLUGIN_ROOT/scripts/audit_directive.py \
        --reports workspace/hthp-2027/panel/round1_*.md \
        --directive workspace/hthp-2027/research/00_개정지시_R2.md

## 왜 이 도구가 생겼나 (2026-08-26, R2 라운드)

평가위원 5인이 R1 에서 각자 **배점 회수표**를 사전 공시했다. 오케스트레이터가 그것을
하나의 개정지시서로 합치면서 **요약**했고, 그 과정에서 항목이 샜다.

| 축 | 위원 회수 ID | 지시서 수록 | R2 결과 |
|---|---:|---:|---|
| 기술성 | 22 | 22 (100%) | **95.25 PASS** |
| 실현가능성 | 19 | 2 (11%) | 68.7 REVISE |
| 근거·정합성 | 20 | 12 (60%) | 71.6 REVISE |
| 사업화·파급 | 18 | 16 (89%) | 89.0 REVISE |

**전건을 옮긴 축만 95 를 넘었다.** 두 위원이 독립적으로 같은 계산을 냈다 —
근거정합성 위원: *「누락 8건 합 12.3점 = 이번 라운드 미회수분 12.3 과 정확히 같습니다.」*

즉 **미달의 원인은 작성자의 이행률이 아니라 지시서의 수록률이었다.**
라운드를 시작하기 전에 기계가 세면 이 부류는 통째로 사라진다.

## 무엇을 재는가

1. **수록률** — 위원 보고서의 회수 ID 가 지시서에 나타나는가
2. **도달 가능 상한** — 지시서에 실린 항목의 회수 배점 합이 필요 회수에 닿는가

★ 2번이 핵심이다. 수록률이 90% 여도 **빠진 10% 가 큰 배점이면 라운드는 시작부터 실패**다.

## 종료 코드

    0  전 축 수록률 100%
    2  누락 있음 — **작성자를 부르지 않는다**
"""
from __future__ import annotations

import argparse
import glob
import io
import os
import re
import sys

# 위원들이 쓰는 회수 ID 라벨. 축마다 접두사가 다르다.
#   기술성 D-/T-/C-/Q-  실현가능성 B-  근거정합성 A-  사업화 G-  형식 G-/N-/W-
#
# ★ 2026-09-07 — 접두사를 **1~2 글자**로 넓혔다.
#   전에는 `[A-Z]` 한 글자만 봤다. 형식 위원에게 기계 게이트 ID(F-4·F-8c)와
#   겹치지 말라고 `FX-` 를 주자 **감사가 그 축을 한 건도 못 봤다.**
#   그러면 「0건 중 0건 = 100%」로 초록불이 난다 — 누락을 잡으려고 만든
#   도구가 누락을 감춘다. 두 글자 오탐은 「행의 마지막 칸이 배점」 조건이 막는다.
ID = re.compile(r"\b([A-Z]{1,2})-(\d+)([a-z])?\b")

# 「| **B-17** | … | +3.0 |」 형태의 표 행에서 배점을 뽑는다.
# ★ 첫 칸이 ID 「만」인 축(기술성)과 「ID + 설명」인 축(사업화·형식)이 섞여 있다.
#   첫 칸의 **앞부분**이 ID 면 회수표 행 후보로 본다.
ROW = re.compile(r"^\|\s*\**([A-Z]{1,2}-\d+[a-z]?)\**[\s가-힣].*$|^\|\s*\**([A-Z]{1,2}-\d+[a-z]?)\**\s*\|")


# 회수 배점 칸은 **반드시 `+` 를 달고 있다.** 누계 열(`64.0`)과 이것으로 갈린다.
CELL_PTS = re.compile(r"^\**\+?\s*([\d.]+)\**\s*(?:\D[^\d]*)?$")
#   ★ 2026-09-07 — `+` 강제를 풀었다(`\+` → `\+?`).
#   형식 위원이 배점을 `**5.0**` 으로 적자 **18건이 통째로 버려졌다.**
#   위원은 이 파서의 표기 관습을 알 수 없다 — 관습에 의존하는 파서는
#   조용히 빈값을 낸다. 누계 열과의 혼동은 ROW 가 「행 첫 칸이 회수 ID」를
#   이미 요구하므로 그쪽이 막는다.


def ids_with_points(path: str) -> dict[str, float]:
    """**배점 회수표의 행만** 뽑는다 → (회수 ID → 배점).

    ★ 처음에는 문서 전체에서 `X-N` 패턴을 긁었다가 소음에 묻혔다 —
      체크리스트 항목(A-1), 고지 항목(J-6), 천장 표시(T-4)까지 회수 항목으로 세고,
      본문 수치(`+3.9%p`)를 배점으로 잘못 읽었다.

      회수표의 유일한 서명은 **「행의 마지막 칸이 배점 숫자 하나」** 다.
      그 조건을 만족하는 행만 센다. 배점 없는 언급은 회수 항목이 아니다.
    """
    out: dict[str, float] = {}

    # ★ 2026-09-07 — 범위를 **「회수표」 절 안으로 좁힌다.**
    #   전에는 문서 전체의 모든 칸을 훑어 **첫 번째** 숫자를 배점으로 쏴다.
    #   도크스트링은 「행의 마지막 칸」이라 적혀 있었으니 둘이 서로 달랐다.
    #   그 차이는 `+` 가 배점을 표시해 주는 동안에만 가려져 있었고,
    #   형식 위원이 `**5.0**` 으로 적자 18건이 통째로 버려졌다.
    #   `+` 를 풀면 이번에는 자수 재원표·행 번호가 배점으로 들어왔다
    #   (실측: 실현가능성 축이 37.5 → 372.5).
    #   둘 다 「모양으로 추측」해서 생긴 일이다. 절로 가른다.
    lines = io.open(path, encoding="utf-8").read().splitlines()
    SEP = re.compile(r"^\|[\s\-:|]+\|$")

    in_sec, prev, ok_tbl = False, "", False
    for ln in lines:
        if ln.startswith("#"):
            in_sec = "회수표" in ln.replace(" ", "")
            ok_tbl = False
        elif SEP.match(ln.strip()):
            # 구분선 바로 앞 줄이 헤더다. ★ 헤더에 「배점」이 있는 표만 읽는다 —
            #   같은 「회수표」 절 안에 자수 누계표가 하나 더 있어
            #   마지막 칸만 보면 자수를 배점으로 읽는다(실측 37.5 → 372.5).
            ok_tbl = (("배점" in prev) or ("회수" in prev)) and "누계" not in prev
        elif in_sec and ok_tbl and ln.startswith("|"):
            m = ROW.match(ln.rstrip())
            if m:
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                hit = CELL_PTS.match(cells[-1]) if cells else None
                # ★ 배점이 없어도 **항목으로는 센다**(2026-09-07).
                #   헤더로 검증된 회수표 안이므로 이 행은 회수 항목이 맞다.
                #   실현가능성 B-15 는 「순증을 흡수할 절감 172자」라 배점이 0 이다 —
                #   배점이 없다고 빼면 **분량 상쇄 지시가 지시서에서 사라져도 감사가 모른다.**
                out.setdefault(m.group(1) or m.group(2),
                               float(hit.group(1)) if hit else 0.0)
        prev = ln
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", nargs="+", required=True,
                    help="위원 보고서 (glob 가능)")
    ap.add_argument("--directive", required=True, help="개정지시서")
    ap.add_argument("--need", action="append", default=[],
                    help="축별 필요 회수. 예: --need 실현가능성=48.0")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    paths: list[str] = []
    for pat in a.reports:
        paths.extend(sorted(glob.glob(pat)))
    if not paths:
        print("보고서를 찾지 못했다"); return 2

    directive = io.open(a.directive, encoding="utf-8").read()
    need = {}
    for n in a.need:
        k, _, v = n.partition("=")
        need[k] = float(v)

    print("=" * 74)
    print(f"지시서 수록률 감사 — {os.path.basename(a.directive)}")
    print("=" * 74)
    print(f"{'축':<14}{'회수 ID':>8}{'수록':>6}{'수록률':>8}"
          f"{'수록 배점':>10}{'누락 배점':>10}  판정")

    bad = False
    for p in paths:
        axis = re.sub(r"^round\d+_|\.md$", "", os.path.basename(p))
        table = ids_with_points(p)
        hit, miss = [], []
        for rid in table:
            if re.search(r"\b%s\b" % re.escape(rid), directive):
                hit.append(rid)
            else:
                miss.append(rid)
        got = sum(table[r] or 0.0 for r in hit)
        lost = sum(table[r] or 0.0 for r in miss)
        rate = len(hit) / max(1, len(table))
        # ★ 0건 축을 통과시키지 않는다 (2026-09-07).
        #   REVISE 판정을 낸 보고서에 회수 항목이 0건일 수는 없다.
        #   0건이면 「옮길 게 없었다」가 아니라 **파서가 그 축을 못 읽은 것**이다.
        #   전에는 miss 가 비어 있다는 이유로 OK 가 나갔다 —
        #   「0건 중 0건 = 100%」. 누락을 잡는 도구가 누락을 감췄다.
        empty = not table
        mark = "★못읽음" if empty else ("OK" if not miss else "누락")
        if miss or empty:
            bad = True
        if empty:
            print(f"{axis:<14}{0:>8}{0:>6}{'-':>8}{0.0:>10.1f}{0.0:>10.1f}  {mark}")
            print(f"    ★ 이 축의 회수표를 한 건도 읽지 못했다. 배점 칸 표기를 확인하라 "
                  f"(마지막 칸이 숫자여야 한다).")
            continue
        print(f"{axis:<14}{len(table):>8}{len(hit):>6}{rate:>7.0%}"
              f"{got:>10.1f}{lost:>10.1f}  {mark}")
        if miss:
            print(f"    빠진 것: {' '.join(sorted(miss)[:14])}"
                  + (" …" if len(miss) > 14 else ""))
            if axis in need and got < need[axis]:
                print(f"    ★ 도달 불가 — 수록 배점 {got:.1f} < 필요 회수 "
                      f"{need[axis]:.1f}. 이 라운드는 시작부터 실패다")

    print()
    if bad:
        print("수록률이 100% 가 아니다(또는 못 읽은 축이 있다). **작성자를 부르지 않는다.**")
        print("회수표를 다시 쓰지 말고 「round1_<축>.md 의 회수표 전건을 이행하라」로 넘겨라.")
        return 2
    print("전 축 수록률 100%.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
