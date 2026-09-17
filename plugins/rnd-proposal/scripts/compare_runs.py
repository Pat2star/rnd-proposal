# -*- coding: utf-8 -*-
"""회차 간 재현성 비교 — 같은 입력으로 N회 돌린 결과물이 얼마나 같은가.

    python $CLAUDE_PLUGIN_ROOT/scripts/compare_runs.py workspace/ai-refrigerant/run*/30_proposal.md

류박사님 전언의 **「일관된 결과물이 나오는지 확인」** 을 재는 도구다.
원 하네스 문서의 실측(골격 없이 쓰면 서술 유사도 0.62)을 이 환경에서 재측정한다.

재는 축
    구조   절 제목 집합 · 1/2수준 항목 수 · 표 개수 · 그림 개수
    수치   단위가 붙은 수치 토큰 다중집합
    서술   문자 3-gram Jaccard (쌍별)
    분량   산문 자수

★ 유사도를 하나만 보면 오해한다. **구조는 같은데 서술이 다른 것**과
  **구조부터 다른 것**은 전혀 다른 문제다. 그래서 축을 나눠 낸다.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from itertools import combinations

NUM = re.compile(r"\d[\d,.]*\s?(?:%|℃|°C|MWth|MW|kW|억원|만원|천원|개월|시간|"
                 r"g/day|t/h|kg|bar|MPa|배|년|건|명|쪽|K|p)(?![A-Za-z0-9])")


def load(p: str) -> str:
    with open(p, encoding="utf-8") as f:
        return f.read()


def structure(md: str) -> dict:
    heads, l1, l2, tbl, fig = [], 0, 0, 0, 0
    in_tbl = False
    for line in md.splitlines():
        s = line.rstrip()
        if s.startswith("#"):
            heads.append(re.sub(r"^#+\s*", "", s).strip())
        elif re.match(r"^\s{2,}[-*]\s", s):
            l2 += 1
        elif re.match(r"^[-*]\s", s):
            l1 += 1
        if s.strip().startswith("|") and s.strip().endswith("|"):
            if not in_tbl:
                tbl += 1
                in_tbl = True
        else:
            in_tbl = False
        if re.search(r"!\[.*?\]\(|\[FIG-\d", s):
            fig += 1
    return {"headings": heads, "l1": l1, "l2": l2, "tables": tbl, "figures": fig}


COMMENT = re.compile(r"<!--.*?-->", re.S)


def prose(md: str) -> str:
    """표·코드·주석을 뺀 서술 텍스트.

    ★ 실측 결함: 예전에는 `<!--` 로 **시작하는 줄**만 걸렀다. 하네스의
    `FORM-GUIDE` 주석은 **여러 줄**이라 본문만 걸러지고 나머지가 산문에 섞였다.
    그 주석은 스캐폴드가 만든 것이라 **회차마다 완전히 동일**하다 —
    즉 유사도를 인위적으로 끌어올린다. 블록 단위로 먼저 제거한다.
    """
    md = COMMENT.sub(" ", md)
    out = []
    for line in md.splitlines():
        s = line.strip()
        if not s or s.startswith("|") or s.startswith("```"):
            continue
        out.append(re.sub(r"^#+\s*|^\s*[-*]\s*", "", s))
    return re.sub(r"\s+", "", " ".join(out))


def grams(t: str, n: int = 3) -> set:
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if (a | b) else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    runs = []
    for p in a.files:
        if not os.path.exists(p):
            print(f"  [없음] {p}")
            continue
        md = load(p)
        st = structure(md)
        pr = prose(md)
        runs.append({"path": p, "name": os.path.basename(os.path.dirname(p)),
                     "st": st, "prose": pr, "g": grams(pr),
                     "nums": sorted(set(re.sub(r"\s+", "", m.group(0))
                                        for m in NUM.finditer(md)))})
    if len(runs) < 2:
        print("비교하려면 2회 이상 필요하다"); return 2

    print("=" * 68)
    print("회차별 규모")
    print("=" * 68)
    print(f"{'회차':<8}{'절':>5}{'1수준':>7}{'2수준':>7}{'표':>5}{'그림':>5}{'산문자수':>10}")
    for r in runs:
        s = r["st"]
        print(f"{r['name']:<8}{len(s['headings']):>5}{s['l1']:>7}{s['l2']:>7}"
              f"{s['tables']:>5}{s['figures']:>5}{len(r['prose']):>10}")

    def spread(vals):
        return f"{min(vals)}~{max(vals)}", (max(vals) - min(vals)) / max(1, max(vals))

    print()
    print("=" * 68)
    print("구조 일관성")
    print("=" * 68)
    for key, label in (("headings", "절 개수"), ("l1", "1수준 항목"),
                       ("l2", "2수준 항목"), ("tables", "표"), ("figures", "그림")):
        vals = [len(r["st"][key]) if key == "headings" else r["st"][key] for r in runs]
        rng, rel = spread(vals)
        mark = "✔" if rel <= 0.10 else ("△" if rel <= 0.30 else "✖")
        print(f"  {mark} {label:<12} {rng:<12} 편차 {rel:.0%}")

    # 절 제목 집합 일치
    sets = [set(r["st"]["headings"]) for r in runs]
    common = set.intersection(*sets)
    union = set.union(*sets)
    print(f"  {'✔' if len(common)==len(union) else '△'} 절 제목 집합   "
          f"공통 {len(common)} / 합집합 {len(union)}  일치율 {len(common)/max(1,len(union)):.0%}")
    only = union - common
    if only:
        print(f"      회차마다 다른 제목 {len(only)}건: {sorted(only)[:5]}")

    print()
    print("=" * 68)
    print("서술 유사도 (문자 3-gram Jaccard)")
    print("=" * 68)
    sims = []
    for x, y in combinations(runs, 2):
        s = jaccard(x["g"], y["g"])
        sims.append(s)
        print(f"  {x['name']} ↔ {y['name']}   {s:.3f}")
    print(f"  평균 {sum(sims)/len(sims):.3f}")
    print("  ※ 원 하네스 문서의 실측 기준선: 골격 없이 쓰면 0.62")

    print()
    print("=" * 68)
    print("수치 토큰 일관성")
    print("=" * 68)
    nsets = [set(r["nums"]) for r in runs]
    ncommon, nunion = set.intersection(*nsets), set.union(*nsets)
    print(f"  공통 {len(ncommon)} / 합집합 {len(nunion)}  "
          f"일치율 {len(ncommon)/max(1,len(nunion)):.0%}")
    for r in runs:
        uniq = set(r["nums"]) - ncommon
        if uniq:
            print(f"  {r['name']} 에만 있는 수치 {len(uniq)}건: {sorted(uniq)[:8]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
