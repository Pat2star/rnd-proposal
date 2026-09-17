#!/usr/bin/env python3
"""양식 설명문(가이드 주석) 제거 — 조립 직전 필수 단계.

`form_scaffold.py` 가 심은 `<!--FORM-GUIDE …-->` 블록과 그 밖의 HTML 주석을 제거해
**조립용 원고**를 따로 만든다. 원본 원고는 건드리지 않는다 — 다음 개정 라운드에서
가이드를 다시 봐야 하기 때문이다.

  30_proposal.md  (가이드 주석 포함, 사람이 고치는 원본)
        └─ form_strip.py ─→  30_proposal.build.md  (주석 0건, kordoc 입력)

★ 왜 지워야 하나: 양식의 설명문("연구의 한 줄 요약이 드러나도록 기재" 등)이 산출물에 남으면
   양식 미준수로 형식 축에서 감점된다. 주석은 마크다운 렌더러에 따라 **그대로 인쇄되기도 한다.**

사용:
  python3 form_strip.py --in 30_proposal.md --out 30_proposal.build.md [--spec form_spec.json]

종료코드 0=제거 완료(잔존 0), 1=잔존 검출, 2=실행 오류.
"""
import argparse, json, re, sys

GUIDE_BLOCK = re.compile(r"<!--\s*FORM-GUIDE.*?-->", re.S)
ANY_COMMENT = re.compile(r"<!--.*?-->", re.S)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # [PATCH] cp949 콘솔 크래시 방지
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    ap.add_argument("--spec", help="양식 명세 JSON — 설명문 잔존(주석 밖에 붙여넣은 경우) 대조용")
    ap.add_argument("--keep-other-comments", action="store_true",
                    help="FORM-GUIDE 이외의 HTML 주석은 남긴다(기본: 전부 제거)")
    a = ap.parse_args()

    text = open(a.src, encoding="utf-8").read()
    n_guide = len(GUIDE_BLOCK.findall(text))
    text = GUIDE_BLOCK.sub("", text)
    n_other = 0
    if not a.keep_other_comments:
        n_other = len(ANY_COMMENT.findall(text))
        text = ANY_COMMENT.sub("", text)
    # 주석 제거로 생긴 3줄 이상 빈 줄을 2줄로 정리 (kordoc 문단 분리 유지)
    text = re.sub(r"\n{3,}", "\n\n", text).lstrip("\n")
    open(a.dst, "w", encoding="utf-8").write(text)

    print(f"가이드 주석 제거 {n_guide}건" + (f" · 기타 주석 {n_other}건" if n_other else ""))

    fails = []
    if "<!--" in text or "-->" in text:
        fails.append("주석 기호 잔존")
    if "FORM-GUIDE" in text:
        fails.append("FORM-GUIDE 문자열 잔존")

    # 주석을 지웠어도 설명문을 본문에 그대로 붙여넣은 경우를 잡는다
    if a.spec:
        spec = json.load(open(a.spec, encoding="utf-8"))
        flat = re.sub(r"\s+", "", text)
        # 양식이 「본문에 그대로 쓰라」고 준 표제(가./나./다./라., [표 A] 등)는 잔존이 아니다
        exempt = [re.sub(r"\s+", "", e) for e in spec.get("residue_exempt", [])]
        hit = []
        for g in [x for n in spec["outline"] for x in (n.get("guide") or [])]:
            probe = re.sub(r"\s+", "", g.split(":")[-1])
            if any(e in probe for e in exempt):
                continue
            if len(probe) >= 12 and probe in flat:
                hit.append(g[:40])
        for pat in spec.get("guide_residue_patterns", []):
            if re.search(pat, text):
                hit.append(pat)
        if hit:
            fails.append(f"양식 설명문이 본문에 남아 있다 {len(hit)}건: {hit[:3]}")

    if fails:
        print("FAIL — " + " · ".join(fails))
        return 1
    print(f"PASS — 잔존 0건 · 조립용 원고: {a.dst} ({len(text):,}자)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"실행 오류: {e}")
        sys.exit(2)
