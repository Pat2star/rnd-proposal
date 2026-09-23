# -*- coding: utf-8 -*-
"""심사 배점표를 기계로 재는 검사기 (2026-09-23).

## 왜 만들었나 — 81점을 맞고서야 만들었다

제출본이 AI 심사에서 **100점 만점에 81점**을 받았다. 19점이 어디서 빠졌는지
심사평에 그대로 적혀 있었고, **가장 큰 손실은 기계가 잡을 수 있는 것이었다.**

    양식 일관성      9/15  (-6)   ← 줄간격이 문서 안에서 갈렸다
    논리적 일관성   16/20  (-4)   ← 전 조건 동시 충족 vs 미달 시 절충
    구체성·명확성   16/20  (-4)   ← 핵심 실행 조건이 비었다
    간결성·전달력   12/15  (-3)   ← 같은 말이 여러 절에 반복
    단어·문체        8/10  (-2)   ← 지나치게 압축돼 의미가 모호
    구조·형식       20/20  ( 0)

심사평은 이렇게 적었다 — *「문단의 약 절반에 130% 줄간격이 적용되고 70% 줄간격도
일부 포함되어 160% 서식이 문서 전반에 일관되게 유지되지 않았습니다」*.

실측해 보니 **한 자도 틀리지 않았다.**

    160%  196문단 (48.8%)   ← 표 밖 본문
    130%  204문단 (50.7%)   ← 전부 표 안
     70%    2문단           ← 역시 표 안

우리 게이트는 **표 밖 본문만 재고 통과시켰다.** 사람 눈에도 안 보인다 —
표 안이 좁은 것은 자연스러워 보이기 때문이다. 문서 전체를 세야 보인다.

**배점이 큰 항목부터 잰다.** 이 파일의 검사 순서가 곧 우선순위다.

## 무엇을 재고 무엇을 안 재나

기계가 재는 것은 **셀 수 있는 것**뿐이다. 「설득력」은 못 잰다.
못 재는 것은 `rp-reviewer` 와 외부 검토(`rp-proofread`)로 넘긴다.

    R1 줄간격 단일성      전 문단(표 안 포함)이 규정값인가        실패
    R2 논리 충돌          상충하는 문장쌍이 같이 있는가            실패
    R3 실행 조건 명시     심사가 이름을 댄 조건이 본문에 있는가    실패
    R4 중복 서술          같은 말이 여러 절에 반복되는가           경고
    R5 과압축             조사·서술어가 빠져 뜻이 모호한가         경고

사용:
    python $CLAUDE_PLUGIN_ROOT/scripts/check_rubric.py --md <build.md> [--hwpx <out.hwpx>]
                                   [--spec <50_form_spec.json>] [--strict]

exit: 0 통과 / 2 실패(--strict 면 경고도 실패)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter

try:                                   # 콘솔이 cp949 여도 깨지지 않게
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── R2 논리 충돌 ────────────────────────────────────────────────────────────
#   실측으로 걸린 쌍을 적는다. 「전부 만족해야 한다」와 「하나는 포기할 수 있다」가
#   같은 문서에 있으면 심사자는 판정 원칙이 없다고 본다.
CONFLICTS = [
    (r"한 조건이라도 누락|모두 충족|동시에 충족|세 가지를 모두",
     r"절충안|우선순위를 정해.{0,10}선택|일부만 달성|타협",
     "전 조건 동시 충족을 요구하면서 미달 시 절충을 허용한다 — 판정 원칙이 둘이다"),
]
#   ★ 규칙을 짐작으로 늘리지 않는다. 「여유가 없다 ↔ 순연된다」를 한 번 넣었다가
#     걷어냈다 — 「여유가 없으니 병렬 배치한다」는 모순이 아니라 대응이었다.
#     **실측으로 걸린 쌍만 적는다.** 짐작한 규칙은 거짓 양성만 만든다.

# ── R3 실행 조건 ────────────────────────────────────────────────────────────
#   심사평이 이름을 대어 「구체화가 부족하다」고 한 것들이다.
#   에너지·소재 계열 계획서의 공통 빈칸이라 기본값으로 둔다.
#   양식마다 다르면 명세 `rubric.required_conditions` 로 덮어쓴다.
CONDITIONS = {
    "모델 구성": r"생성 모델은|모델 구조|신경망|SMILES|회귀기|아키텍처",
    "학습 데이터 규모": r"학습셋|학습 데이터|DB\s*수천|만 건|종 규모|데이터 규모",
    "판정 기준": r"판정하며|판정 기준|등급 상당|기준으로 둠|합격 기준",
    "시험 운전조건": r"운전조건은|증발 .{0,12}℃|응축 .{0,12}℃|과열 .{0,4}K",
    "대상 상태영역": r"상태영역은|상태 영역은|포화·과열|압력 범위",
}


def _paragraph_spacing(path: str) -> Counter:
    """HWPX 전 문단의 줄간격 — **표 안을 포함한다.** 이게 요점이다."""
    z = zipfile.ZipFile(path)
    hdr = z.read("Contents/header.xml").decode("utf-8")
    sec = "".join(z.read(n).decode("utf-8") for n in sorted(z.namelist())
                  if re.fullmatch(r"Contents/section\d+\.xml", n))
    sp = {}
    for m in re.finditer(r'<hh:paraPr id="(\d+)"(.*?)</hh:paraPr>', hdr, re.S):
        ls = re.search(r'<hh:lineSpacing[^>]*type="([^"]*)"[^>]*value="(-?\d+)"',
                       m.group(2))
        if ls:
            sp[m.group(1)] = (ls.group(1), int(ls.group(2)))
    return Counter(sp.get(i, ("?", 0))
                   for i in re.findall(r'<hp:p\b[^>]*paraPrIDRef="(\d+)"', sec))


def _sections(md: str) -> dict[str, list[str]]:
    """절 제목 → 그 절의 슬롯 목록."""
    out, cur = {}, "(머리말)"
    for ln in md.split("\n"):
        h = re.match(r"^#{2,4}\s+(.+)$", ln)
        if h:
            cur = h.group(1).strip()
            out.setdefault(cur, [])
        elif ln.startswith("  - "):
            out.setdefault(cur, []).append(ln[4:].strip())
    return out


def _shingles(t: str, n: int = 4) -> set[str]:
    """이어지는 낱말 n개의 창.

    ★ 창 크기를 실측으로 골랐다(2026-09-23). 제출본(81점)에 대고 재 보니
      n=6 은 **0쌍**(심사는 중복을 지적했는데 못 잡았다), n=3 은 9쌍인데
      「HFCs 관리제도 개선방안」 같은 고유명사까지 걸렸다.
      **n=4 에서 심사가 이름을 댄 중복(1-1 ↔ 4-1 「적용처는 12 kW 미만」)만
      남았다.**

    출처·특허번호를 두 절에서 다시 인용하는 것은 중복이 아니므로 뺀다.
    """
    w = re.sub(r"[^\w가-힣]+", " ", t).split()
    out = set()
    for i in range(max(0, len(w) - n + 1)):
        win = w[i:i + n]
        if sum(bool(re.fullmatch(r"[A-Za-z0-9]+", x)) for x in win) >= n - 1:
            continue                      # 특허번호·영문 기관명 재인용
        out.add(" ".join(win))
    return out


def check(md_path, hwpx_path=None, spec_path=None):
    md = open(md_path, encoding="utf-8").read()
    spec = json.load(open(spec_path, encoding="utf-8")) if spec_path else {}
    rub = spec.get("rubric") or {}
    fails, warns = [], []

    # ── R1 줄간격 단일성 (배점 손실 1위) ────────────────────────────────────
    want = (spec.get("style") or {}).get("line_spacing")
    if hwpx_path and want:
        cnt = _paragraph_spacing(hwpx_path)
        tot = sum(cnt.values()) or 1
        off = {k: v for k, v in cnt.items() if k != ("PERCENT", int(want))}
        detail = " · ".join(f"{k[0]} {k[1]}: {v}문단({v / tot * 100:.1f}%)"
                            for k, v in sorted(off.items()))
        if off:
            fails.append(("R1 줄간격 단일성",
                          f"규정 {want}% 와 다른 문단 {sum(off.values())}/{tot} — {detail}"))
        else:
            print(f"[OK ] R1 줄간격 단일성      전 {tot}문단 {want}% (표 안 포함)")
    elif want:
        warns.append(("R1 줄간격 단일성", "hwpx 를 주지 않아 못 쟀다"))

    # ── R2 논리 충돌 ────────────────────────────────────────────────────────
    hit = []
    for a, b, why in CONFLICTS + [tuple(x) for x in rub.get("conflicts", [])]:
        ma = [m.group(0) for m in re.finditer(a, md)]
        mb = [m.group(0) for m in re.finditer(b, md)]
        if ma and mb:
            hit.append(f"{why} ({ma[0]} ↔ {mb[0]})")
    if hit:
        fails.append(("R2 논리 충돌", " / ".join(hit)))
    else:
        print("[OK ] R2 논리 충돌          상충 쌍 0건")

    # ── R3 실행 조건 명시 ───────────────────────────────────────────────────
    conds = dict(CONDITIONS)
    conds.update(rub.get("required_conditions") or {})
    missing = [k for k, pat in conds.items() if not re.search(pat, md)]
    if missing:
        fails.append(("R3 실행 조건 명시", f"본문에 없다 — {', '.join(missing)}"))
    else:
        print(f"[OK ] R3 실행 조건 명시     {len(conds)}항목 전부 있음")

    # ── R4 중복 서술 ────────────────────────────────────────────────────────
    secs = _sections(md)
    dup = []
    keys = list(secs)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            for sa in secs[a]:
                for sb in secs[b]:
                    if len(sa) < 20 or len(sb) < 20:
                        continue
                    sh = _shingles(sa) & _shingles(sb)
                    if sh:
                        dup.append(f"{a} ↔ {b}: 「{list(sh)[0][:34]}…」")
    dup = sorted(set(dup))
    if dup:
        warns.append(("R4 중복 서술", f"{len(dup)}쌍 — " + " / ".join(dup[:3])))
    else:
        print("[OK ] R4 중복 서술          절 간 반복 0건")

    # ── R5 과압축 ───────────────────────────────────────────────────────────
    #   심사평: 「일부 표현이 지나치게 압축되거나 의미가 모호하여 문장 정확성이
    #   다소 떨어집니다」. 셀 수 있는 신호만 본다.
    slots = re.findall(r"^  - (.+)$", md, re.M)
    terse = []
    for t in slots:
        why = []
        # 쉼표가 **절**을 잇는데 연결 어미가 없다.
        #   ★ 단순 열거(「A 93억, B 115억」)는 개조식에서 정상이다 — 실측에서
        #     9건이 잡혔고 대부분 정당한 열거였다. 쉼표 **양쪽이 모두 주어를
        #     가질 때만** 절 접속으로 본다.
        core = re.sub(r"\d,\d", "", t)
        if "," in core and not re.search(
                r"(이며|하며|이고|하고|으며|되며|라서|므로|어서|지만|인데)", t):
            parts = [x for x in core.split(",") if x.strip()]
            subj = sum(bool(re.search(r"[가-힣](은|는|이|가)\s", x)) for x in parts)
            if len(parts) >= 2 and subj >= 2:
                why.append("절이 쉼표로만 이어짐")
        # 조사 앞이 떨어졌다 (「B2 는」)
        if re.search(r"[A-Za-z0-9] (는|은|이|가|를|을)\s", t):
            why.append("조사 분리")
        if why:
            terse.append(f"{'·'.join(why)} | {t[:40]}")
    if terse:
        warns.append(("R5 과압축", f"{len(terse)}건 — " + " / ".join(terse[:3])))
    else:
        print("[OK ] R5 과압축             0건")

    for name, msg in fails:
        print(f"[FAIL] {name}  {msg}")
    for name, msg in warns:
        print(f"[WARN] {name}  {msg}")
    return fails, warns


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True)
    ap.add_argument("--hwpx")
    ap.add_argument("--spec")
    ap.add_argument("--strict", action="store_true", help="경고도 실패로 본다")
    a = ap.parse_args()

    print("=" * 62)
    print("심사 배점 검사 — 손실이 큰 항목부터")
    print("=" * 62)
    fails, warns = check(a.md, a.hwpx, a.spec)
    print("=" * 62)
    if fails or (a.strict and warns):
        print(f"FAIL — 실패 {len(fails)}건 · 경고 {len(warns)}건")
        return 2
    print(f"PASS — 실패 0건 · 경고 {len(warns)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
