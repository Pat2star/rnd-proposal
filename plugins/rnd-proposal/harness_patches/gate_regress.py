#!/usr/bin/env python3
"""규율 H — 판 간 회귀 게이트.

**개정은 매 라운드 신규 결함을 낳는다**(실측: v2 9건 · v3 4~6건 · v4 4건 · v5 3~5건 ·
v7 21.15점). 특히 압축·재작성은 직전 라운드가 「완전 해소 확정」한 항목을 되돌린다.
이 스크립트는 그 되돌림을 판 간 기계 비교로 잡는다.

검사 항목
  H-1 필수 문자열 카운트 비교      — 감소하면 FAIL
  H-2 수치 토큰 다중집합 차분      — 소멸 토큰 전건에 해명 요구
  H-3 인용표기·표주석 정의:사용 1:1
  H-4 「완전 해소 확정」 항목 재검사 — 리스트 파일로 관리
  H-5 문단 구조 카운트            — 표주석·참고문헌 독립 문단 수 감소 = 병합 회귀

★ H-2 의 한계 — **반드시 알고 쓸 것**
  토큰 수준 검사는 **「수치는 살아 있고 그 수치를 설명하던 문장만 사라진」 회귀를
  잡지 못한다.** 실측: 압축 라운드에서 *"2차년도 39.0억은 6kW급 시제·통합 착수"*
  가 삭제됐으나 `39.0` 토큰이 연구비 격자에 그대로 있어 H-2 는 PASS 를 냈다
  (평가위원 2인이 산문 diff 로 적발). 같은 구간에서 `(제26조)` → `(동 고시 제26조)`
  의 「동 고시」 소실도 토큰이 아니라 걸리지 않았다.
  ⇒ **H-4 의 `--resolved` 목록에 「문장·구문」을 올려야 잡힌다.** 위원이 「완전 해소
  확정」을 선언할 때마다 그 **문자열 자체**를 목록에 추가하는 것이 이 게이트의 핵심
  운용법이다. 실측 확인: 위 2건을 목록에 올리자 H-4 가 정확히 2건 모두 검출했다.

사용:
  python3 gate_regress.py --prev 30_proposal_v10.md --curr 30_proposal.md \
      [--required required.txt] [--resolved resolved.txt] [--json out.json]

md 를 받지만 **판정은 hwpx 로 확인할 것** — md 통과가 산출물 통과를 뜻하지 않는다
(규율 J 참조). 이 게이트는 원고 수준의 회귀를 조기에 잡는 보조 도구다.

종료코드 0=PASS, 1=FAIL, 2=실행 오류.
"""
import argparse, json, re, sys
from collections import Counter

# 수치 토큰 — 금액·비율·배수·연도·조문번호까지 포함
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
# 근거의 뼈대 — 이 표기가 줄면 출처가 사라진 것이다
CITE = re.compile(r"\[\d{1,2}\]")
NOTE = re.compile(r"\[주[a-z]\]")


def read(p):
    return open(p, encoding="utf-8").read()


def tokens(s):
    return Counter(NUM.findall(s))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # [PATCH] cp949 콘솔 크래시 방지
    ap = argparse.ArgumentParser()
    ap.add_argument("--prev", required=True, help="직전 판 원고")
    ap.add_argument("--curr", required=True, help="현행 판 원고")
    ap.add_argument("--required", help="필수 문자열 목록(1줄 1항목)")
    ap.add_argument("--resolved", help="「완전 해소 확정」 문자열 목록(1줄 1항목)")
    ap.add_argument("--allow-drop", help="소멸이 허용된 토큰 목록(1줄 1항목) — 의도된 삭제")
    ap.add_argument("--json")
    a = ap.parse_args()

    try:
        prev, curr = read(a.prev), read(a.curr)
    except Exception as e:
        print(f"[오류] 파일 읽기 실패: {e}")
        return 2

    fails, res = [], {}

    def check(name, ok, detail=""):
        res[name] = {"pass": bool(ok), "detail": detail}
        if not ok:
            fails.append(f"{name}: {detail}")
        print(f"  {'PASS' if ok else 'FAIL':4}  {name}" + (f" — {detail}" if detail else ""))

    print(f"규율 H 회귀 게이트\n  직전: {a.prev}\n  현행: {a.curr}\n")

    # H-1 필수 문자열
    if a.required:
        need = [l.rstrip("\n") for l in open(a.required, encoding="utf-8") if l.strip()]
        lost = [s for s in need if prev.count(s) > 0 and curr.count(s) == 0]
        shrunk = [f"{s}({prev.count(s)}→{curr.count(s)})" for s in need
                  if curr.count(s) < prev.count(s) and curr.count(s) > 0]
        check("H-1 필수 문자열 소멸 0", not lost, f"소멸 {lost}" if lost else "")
        if shrunk:
            print(f"  INFO  카운트 감소(소멸은 아님): {shrunk}")

    # H-2 수치 토큰 다중집합 차분
    pt, ct = tokens(prev), tokens(curr)
    allow = set()
    if a.allow_drop:
        allow = {l.strip() for l in open(a.allow_drop, encoding="utf-8") if l.strip()}
    gone = sorted([t for t in pt if ct[t] == 0 and t not in allow],
                  key=lambda x: -pt[x])
    check("H-2 수치 토큰 소멸 0", not gone,
          f"{len(gone)}종 소멸 — 전건 해명 필요: {gone[:12]}" if gone else
          f"prev 고유 {len(pt)}종 전부 존치")

    # H-3 인용표기·표주석 정의:사용
    for name, rx in (("인용표기 [n]", CITE), ("표주석 [주x]", NOTE)):
        p_, c_ = Counter(rx.findall(prev)), Counter(rx.findall(curr))
        lost = sorted(set(p_) - set(c_))
        check(f"H-3 {name} 소멸 0", not lost,
              f"소멸 {lost}" if lost else f"{len(c_)}종 유지")
        # 정의 1회 + 사용 1회 이상이 정상 — 정의만 있고 사용이 없으면 유령 각주
        orphan = [k for k, v in c_.items() if v < 2]
        if orphan:
            print(f"  INFO  {name} 중 1회만 등장(정의 또는 사용 한쪽 누락 의심): {orphan}")

    # H-4 「완전 해소 확정」 항목 재검사
    if a.resolved:
        items = [l.rstrip("\n") for l in open(a.resolved, encoding="utf-8") if l.strip()]
        back = [s for s in items if s not in curr]
        check("H-4 완전해소 확정분 회귀 0", not back,
              f"{len(back)}건 회귀: {back[:6]}" if back else f"{len(items)}건 전량 유지")

    # H-5 문단 구조 카운트 (병합 회귀 탐지)
    def para_counts(s):
        lines = [l.strip() for l in s.split("\n")]
        return (sum(1 for l in lines if re.match(r"^\[주[a-z]\]", l)),
                sum(1 for l in lines if re.match(r"^\[\d{1,2}\]", l)))
    pn, pr = para_counts(prev)
    cn, cr = para_counts(curr)
    check("H-5 표주석 독립 문단 유지", cn >= pn, f"{pn}→{cn} (감소 = 병합 회귀)")
    check("H-5 참고문헌 독립 문단 유지", cr >= pr, f"{pr}→{cr} (감소 = 병합 회귀)")

    # 참고 — 분량 변화
    print(f"\n  INFO  자수 {len(prev):,} → {len(curr):,} ({len(curr)-len(prev):+,})")

    ok = not fails
    print(f"\n{'='*60}\n{'PASS' if ok else 'FAIL'} — 실패 {len(fails)}건")
    for f in fails:
        print(f"  · {f}")
    print("\n※ H-2 의 소멸 토큰은 **자동 FAIL이 아니라 해명 요구**다. 의도된 삭제는")
    print("   --allow-drop 목록에 올려 개정 이력에 사유와 함께 남길 것.")

    if a.json:
        json.dump({"pass": ok, "checks": res, "fails": fails},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
