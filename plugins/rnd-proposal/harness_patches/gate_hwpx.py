#!/usr/bin/env python3
"""규율 J — 산출물 구조 게이트.

**존재 검사 단독은 거짓 통과를 발급한다.** 이 스크립트는 md가 아니라 **HWPX 산출물**을
직접 파싱해 구조를 검사한다. 규율 I(존재 검사)는 여기에 흡수됐다.

실측 계보 — 「존재는 있고 구조가 깨진」 결함 3건이 전부 존재 검사를 통과했다:
  1) 참고문헌 20건이 HWPX에서 단일 문단 2,018자로 병합       (존재 검사 통과)
  2) 표주석 [주a]~[주j]가 단일 문단 1,407자로 병합            (존재 검사 통과)
  3) 마크다운 표 중간의 빈 줄 1개가 표를 hp:tbl 2개로 쪼개
     #8행이 머리글 없는 고아 표가 됨 — 2개 판에 승계된 뒤
     평가위원 3인이 독립 적발                                  (「8행 존재」 검사 통과)

사용:
  python3 gate_hwpx.py --hwpx 30_proposal.md.hwpx \
      [--prev 30_proposal_v10.hwpx] [--expect-tables 18] \
      [--required required.txt] [--sections §목록.txt] [--json gate_result.json]

종료코드 0=PASS, 1=FAIL, 2=실행 오류.
"""
import argparse, hashlib, json, re, sys, zipfile
import xml.etree.ElementTree as ET

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS = {"hp": HP}
T = f"{{{HP}}}t"
P = f"{{{HP}}}p"
TBL = f"{{{HP}}}tbl"
TR = f"{{{HP}}}tr"
TC = f"{{{HP}}}tc"
PIC = f"{{{HP}}}pic"

# 금칙 — 실인쇄 사고가 확인된 문자·문자열
FORBIDDEN = {
    "두부 문자 ⚠(U+26A0)": "⚠",
    "이형 공백 U+FEFF": "﻿",
    "미치환 플레이스홀더": "[보완 필요",
    "TODO 잔존": "TODO",
    "미변환 마크다운 강조": "**",
}
# 이중 이스케이프 — 3패턴 전부 검사할 것(1패턴만 보면 놓친다)
ESCAPE_PATTERNS = [r"&amp;amp;", r"&amp;lt;", r"&amp;gt;"]


def local_text(elem):
    """이 hp:p 에 직접 속한 텍스트만 모은다.

    ★ 함정(실측): `.//hp:t` 로 단순 수집하면 **표 셀 텍스트가 표를 품은 문단에 합산**되어
    거짓 FAIL이 난다(818문단·최장 1,264자·1,000자 초과 2건 → 표 내부 제외 시
    154문단·최장 880자·초과 0건). 하위 hp:tbl 을 만나면 내려가지 않는다.
    """
    out = []

    def walk(node):
        for ch in node:
            if ch.tag == TBL:
                continue
            if ch.tag == T:
                out.append(ch.text or "")
            walk(ch)

    walk(elem)
    return "".join(out)


def cell_text(tc):
    return "".join(t.text or "" for t in tc.iter(T))


def load(path):
    z = zipfile.ZipFile(path)
    parts = {n: z.read(n) for n in z.namelist()}
    return z, parts


def table_shapes(root):
    """표를 (순번, rowCnt, colCnt, 첫 셀 40자) 로 덤프."""
    shapes = []
    for i, tbl in enumerate(root.iter(TBL), 1):
        rc = tbl.get("rowCnt") or str(len(list(tbl.iter(TR))))
        cc = tbl.get("colCnt") or ""
        first = ""
        for tc in tbl.iter(TC):
            first = cell_text(tc).strip()[:40]
            break
        shapes.append((i, int(rc) if rc.isdigit() else -1,
                       int(cc) if cc.isdigit() else -1, first))
    return shapes


def grid_check(root):
    """격자 자동 재검산 — 숫자만으로 이뤄진 표의 행합·열합·총계 대조.

    마지막 행/열이 「계」인 표를 찾아, 합이 맞는지 확인한다.
    반올림 표기로 비중 합이 100이 아니면 **자진 고지 문구**가 있는지도 본다.
    """
    findings = []
    num = re.compile(r"^-?[\d,]+(?:\.\d+)?$")

    for idx, tbl in enumerate(root.iter(TBL), 1):
        rows = []
        for tr in tbl.iter(TR):
            rows.append([cell_text(tc).strip().replace("*", "") for tc in tr.iter(TC)])
        if len(rows) < 3:
            continue
        last = rows[-1]
        # ★ 함정(실측): re.search(r"계") 는 「2단계」의 '계' 에도 매칭돼 거짓 FAIL 을 낸다.
        #    합계 행은 첫 셀이 「계/합계/총계/소계」 **그 자체**일 때만 인정한다(부분문자열 금지).
        if not last or not re.fullmatch(r"\s*(계|합계|총계|소계)\s*", last[0]):
            continue
        # 열별 세로합 대조 (헤더 1행 가정, 마지막 행은 계)
        for c in range(1, min(len(last), min(len(r) for r in rows))):
            vals = []
            ok = True
            for r in rows[1:-1]:
                v = r[c].replace(",", "")
                if not num.match(v):
                    ok = False
                    break
                vals.append(float(v))
            tot = last[c].replace(",", "")
            if not ok or not vals or not num.match(tot):
                continue
            s, tv = round(sum(vals), 2), float(tot)
            if abs(s - tv) > 0.051:  # 0.1 단위 반올림 허용
                findings.append(f"표{idx} 제{c+1}열 세로합 불일치: 계산 {s} vs 표기 {tv}")
    return findings


def page_check(raw, paper="A4", want_portrait=True):
    """J-16 용지 규격·방향 정합성.

    ★ 실측 사고(2026-08-13): 산출물이 **A4 세로 치수(210×297mm)인데 `landscape="WIDELY"`(가로)**로
    저장돼 있었다. 치수와 방향 속성이 어긋난 상태이며, 한글이 어느 쪽을 따르느냐에 따라
    다르게 열릴 수 있다. **문서를 열어보기 전에는 드러나지 않는 계열**이라 기계로 검사한다.

    ★★ 값의 의미는 직관과 반대다 (2026-08-13 PDF 실측으로 확정):
      **WIDELY = 세로(Portrait) / NARROWLY = 가로(Landscape)**
    같은 문서를 NARROWLY 로 두면 한글이 297×210mm(가로)로 조판하고, WIDELY 로 두면 210×297mm(세로)다.
    `width`/`height` 속성은 **용지 크기일 뿐 방향을 결정하지 않는다** — 방향은 이 속성이 지배한다.
    검증 방법: 한글 COM 으로 PDF 저장 후 `/MediaBox` 를 읽는다. COM PageSetup 조회는 빈 값을 돌려준다.
    반환: (mm 폭, mm 높이, landscape 값, 문제 목록)
    """
    SPEC = {"A4": (210.0, 297.0), "A3": (297.0, 420.0), "B5": (176.0, 250.0), "Letter": (215.9, 279.4)}
    m = re.search(r"<hp:pagePr[^>]*>", raw)
    if not m:
        return (None, None, None, ["hp:pagePr 미검출"])
    tag = m.group(0)
    def num(k):
        mm = re.search(rf'{k}="(\d+)"', tag)
        return int(mm.group(1)) if mm else None
    w, h = num("width"), num("height")
    ls = re.search(r'landscape="([^"]+)"', tag)
    ls = ls.group(1) if ls else None
    if w is None or h is None:
        return (None, None, ls, ["width/height 미검출"])
    wm, hm = w / 7200 * 25.4, h / 7200 * 25.4
    bad = []
    ORIENT = {"WIDELY": "세로", "NARROWLY": "가로"}
    if ls not in ORIENT:
        bad.append(f"landscape 속성 이상: {ls!r}")
    elif want_portrait and ls != "WIDELY":
        bad.append(f"세로를 요구했는데 landscape={ls}(가로)다 — 「WIDELY = 세로」임에 유의")
    # 규격 대조 (세로/가로 양쪽 허용)
    if paper in SPEC:
        pw, ph = SPEC[paper]
        if not ((abs(wm - pw) < 1.5 and abs(hm - ph) < 1.5) or
                (abs(wm - ph) < 1.5 and abs(hm - pw) < 1.5)):
            bad.append(f"{paper} 규격 불일치: 실측 {wm:.0f}×{hm:.0f}mm (기대 {pw:.0f}×{ph:.0f}mm)")
    return (wm, hm, ORIENT.get(ls, ls), bad)


def table_width_check(raw):
    """J-17 표 폭 ↔ 본문 문단 폭 정합성.

    ★ 실측 사고(2026-08-15): 조립 도구가 **자기 프리셋 여백**(좌우 5,669)으로 표를 만들고,
    우리 조립은 그 뒤에 여백을 **양식값**(좌우 8,504)으로 패치한다. 표는 그대로 남아
    본문 폭 **42,519** 인 문서에 **46,389** 짜리 표가 들어갔다 — 오른쪽 여백을 **13.6mm 침범**한다.
    파일은 열리고 `validate` 도 통과하며 다른 J 항목도 전부 PASS 였다. **인쇄해야 보이는 결함**이다.

    표는 `treatAsChar="1"`(글자처럼 취급)이라 **바깥 좌·우 여백이 폭에 더해진다** — 점유폭으로 본다.
    반환: (본문 폭, [문제 문자열]).
    """
    p = re.search(r"<hp:pagePr\b[^>]*>", raw)
    m = re.search(r"<hp:margin\b[^>]*/?>", raw)
    if not (p and m):
        return (None, [])                     # 구 파이프라인 산출물 — J-16 이 따로 잡는다
    def att(tag, k):
        mm = re.search(rf'{k}="(\d+)"', tag)
        return int(mm.group(1)) if mm else 0
    text = att(p.group(0), "width") - att(m.group(0), "left") - att(m.group(0), "right") \
        - att(m.group(0), "gutter")
    bad, depth, start = [], 0, None
    for mt in re.finditer(r"<hp:tbl\b|</hp:tbl>", raw):
        if mt.group(0) == "</hp:tbl>":
            depth -= 1
            if depth == 0:
                spans = raw[start:mt.end()]
                w = re.search(r'<hp:sz width="(\d+)"', spans)
                om = re.search(r'<hp:outMargin\b[^>]*left="(\d+)"[^>]*right="(\d+)"', spans)
                occ = (int(w.group(1)) if w else 0) + \
                      ((int(om.group(1)) + int(om.group(2))) if om else 0)
                if occ != text:
                    bad.append(f"표{len(bad)+1} 점유 {occ} ≠ 본문 {text} ({occ-text:+d})")
        else:
            if depth == 0:
                start = mt.start()
            depth += 1
    return (text, bad)


def emphasis_check(parts, md_path):
    """J-14 강조(굵기) 소실 — 「존재는 있고 구조가 깨진」 결함 계보의 4번째 사례.

    ★ 실측 사고(2026-08-13): 원고에 굵기 span 594개가 있는데 산출물 header.xml 의
    <hh:bold> 정의가 **0건**이었다. 8라운드 PASS 판정본이 굵은 글씨를 하나도 갖고 있지
    않았고, 표주석 [주k] "굵은 값은 AR5 기준"이 산출물에서 **지시 대상을 잃은** 상태로
    8라운드 내내 아무도 적발하지 못했다. 본문 텍스트는 전량 보존돼 있었으므로
    자수·존재 검사로는 영원히 잡히지 않는다 — 서식 속성을 직접 세야 한다.

    반환: (굵기 charPr 정의 수, 굵기 적용 run 수, 원고 굵기 span 수 또는 None)
    """
    hdr = parts.get("Contents/header.xml", b"").decode("utf-8", "replace")
    bold_ids = set()
    for m in re.finditer(r'<hh:charPr\b[^>]*\bid="(\d+)"[^>]*>(.*?)</hh:charPr>', hdr, re.S):
        if "<hh:bold" in m.group(2):
            bold_ids.add(m.group(1))

    sec = "".join(
        parts[n].decode("utf-8", "replace")
        for n in sorted(parts) if re.match(r"Contents/section\d+\.xml$", n)
    )
    applied = sum(1 for r in re.findall(r'charPrIDRef="(\d+)"', sec) if r in bold_ids)

    src = None
    if md_path:
        try:
            src = open(md_path, encoding="utf-8").read().count("**") // 2
        except Exception:
            src = None
    return len(bold_ids), applied, src


def section_refs(root, valid_sections):
    """§ 상호참조 실존성 — 본문의 §n-m 참조가 실제 절 목록에 있는지.

    ★ 함정(실측) 2건:
      ⑴ hp:t 런을 구분자 없이 이어붙이면 `§3-3` + `45개월` 이 `§3-345` 로 붙어
         **거짓 깨진참조**가 뜬다 → 문단·셀 단위로 모아 개행으로 잇는다.
      ⑵ 미국 CFR 인용 `40 CFR §84.54(a)(10)`·`§84.7` 이 자기 문서의 절 참조로
         오인된다 → `§숫자.숫자` 형태는 외부 법령 인용으로 보고 제외한다.
    """
    chunks = [local_text(p) for p in root.iter(P)]
    for tc in root.iter(TC):
        chunks.append(cell_text(tc))
    body = "\n".join(chunks)
    refs = set(re.findall(r"§\s?\d+(?:-\d+)?(?![\d\-]|\.\d)", body))
    if not valid_sections:
        return sorted(refs), []
    broken = [r for r in refs if r.replace(" ", "") not in valid_sections]
    return sorted(refs), broken


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # [PATCH] cp949 콘솔 크래시 방지
    ap = argparse.ArgumentParser()
    ap.add_argument("--hwpx", required=True)
    ap.add_argument("--prev", help="직전 판 HWPX — 형상 diff·BinData 해시 비교용")
    ap.add_argument("--expect-tables", type=int, help="기대 표 개수(선언값). 불일치면 FAIL")
    ap.add_argument("--required", help="필수 문자열 목록 파일(1줄 1항목)")
    ap.add_argument("--sections", help="실존 절 목록 파일(1줄 1항목, 예 §2-3)")
    ap.add_argument("--md", help="원고 Markdown — J-14 강조(굵기) 보존 대조용")
    ap.add_argument("--titles", help="양식 절 제목 목록 파일(1줄 1제목) — J-15 축자 대조용")
    ap.add_argument("--paper", default="A4", help="용지 규격 — J-16 대조용 (A4/A3/B5/Letter)")
    ap.add_argument("--max-para", type=int, default=1000, help="본문 문단 자수 상한")
    ap.add_argument("--json", help="결과 JSON 출력 경로")
    a = ap.parse_args()

    try:
        z, parts = load(a.hwpx)
    except Exception as e:
        print(f"[오류] HWPX 열기 실패: {e}")
        return 2

    secs = [n for n in parts if re.match(r"Contents/section\d+\.xml$", n)]
    if not secs:
        print("[오류] Contents/section*.xml 없음")
        return 2
    root = ET.fromstring(b"".join(parts[n] for n in sorted(secs))
                         if len(secs) == 1 else parts[sorted(secs)[0]])
    raw = parts[sorted(secs)[0]].decode("utf-8", "replace")

    res, fails = {}, []

    def check(name, ok, detail=""):
        res[name] = {"pass": bool(ok), "detail": detail}
        if not ok:
            fails.append(f"{name}: {detail}")
        print(f"  {'PASS' if ok else 'FAIL':4}  {name}" + (f" — {detail}" if detail else ""))

    print(f"규율 J 산출물 구조 게이트 — {a.hwpx}\n")

    # J-1 표 전수 덤프
    shapes = table_shapes(root)
    print(f"  [표 덤프] {len(shapes)}개")
    for s in shapes:
        print(f"      #{s[0]:<3} {s[1]}행 × {s[2]}열   {s[3]}")
    print()

    # J-2 표 개수 대조 (선언 ↔ 실측)
    if a.expect_tables is not None:
        check("J-2 표 개수 선언 대조", len(shapes) == a.expect_tables,
              f"선언 {a.expect_tables} vs 실측 {len(shapes)}")

    # J-3 고아 표 (rowCnt=1)
    orphans = [s for s in shapes if s[1] == 1]
    check("J-3 고아 표(rowCnt=1) 0개", not orphans,
          f"{len(orphans)}개: {[o[0] for o in orphans]}" if orphans else "")

    # J-4 직전 판 형상 diff
    if a.prev:
        try:
            _, pparts = load(a.prev)
            proot = ET.fromstring(pparts[sorted(
                [n for n in pparts if re.match(r"Contents/section\d+\.xml$", n)])[0]])
            pshapes = table_shapes(proot)
            moved = [(p, c) for p, c in zip(pshapes, shapes)
                     if (p[1], p[2]) != (c[1], c[2])]
            check("J-4 표 형상 판 간 diff",
                  len(pshapes) == len(shapes) and not moved,
                  f"표 수 {len(pshapes)}→{len(shapes)}, 형상변동 {len(moved)}건"
                  f"{[m[1][0] for m in moved] if moved else ''}")
            # J-6 BinData 해시 (판 간 동일성 전용 — 원본 PNG와는 재인코딩으로 달라진다)
            def bd(pp):
                return {k: hashlib.md5(v).hexdigest()
                        for k, v in pp.items() if k.startswith("BinData/")}
            b1, b2 = bd(pparts), bd(parts)
            same = sum(1 for k in b2 if k in b1 and b1[k] == b2[k])
            print(f"  INFO  BinData {len(b2)}건 중 판 간 동일 {same}건 "
                  f"(다르면 재렌더가 실제로 일어난 것)")
        except Exception as e:
            print(f"  WARN  직전 판 비교 실패: {e}")

    # J-5 본문 문단 자수 (★ 표 내부 제외)
    paras = [local_text(p) for p in root.iter(P)]
    body = [t for t in paras if t.strip()]
    over = [len(t) for t in body if len(t) > a.max_para]
    check(f"J-5 본문 문단 {a.max_para}자 초과 0", not over,
          f"{len(over)}건 {over}" if over else f"본문 {len(body)}문단, 최장 {max((len(t) for t in body), default=0)}자")

    # J-6 각주·표주석 독립 문단
    notes = [t for t in body if re.match(r"^\[주[a-z]\]", t.strip())]
    refs_ = [t for t in body if re.match(r"^\[\d+\]", t.strip())]
    print(f"  INFO  표주석 독립 문단 {len(notes)}개 / 참고문헌 독립 문단 {len(refs_)}개"
          f"  ← 판 간 감소하면 병합 회귀다")

    # J-7 이중 이스케이프 (3패턴 전부)
    esc = {p: len(re.findall(p, raw)) for p in ESCAPE_PATTERNS}
    check("J-7 이중 이스케이프 0건", not any(esc.values()),
          ", ".join(f"{k}={v}" for k, v in esc.items() if v))

    # J-8 전 XML 파트의 선언 보유
    noxml = [n for n, v in parts.items()
             if n.endswith(".xml") and not v.lstrip()[:5].startswith(b"<?xml")]
    check("J-8 XML 선언 전 파트 보유", not noxml, f"누락: {noxml}" if noxml else f"{sum(1 for n in parts if n.endswith('.xml'))}개 파트")

    # J-9 금칙·플레이스홀더
    hits = {k: raw.count(v) for k, v in FORBIDDEN.items() if raw.count(v)}
    check("J-9 금칙·플레이스홀더 0건", not hits, str(hits) if hits else "")

    # J-10 그림
    npic = len(list(root.iter(PIC)))
    nbin = sum(1 for n in parts if n.startswith("BinData/"))
    check("J-10 그림 객체 ↔ BinData 정합", npic <= nbin and npic > 0 or npic == nbin,
          f"hp:pic {npic} / BinData {nbin}")

    # J-11 격자 재검산
    g = grid_check(root)
    check("J-11 격자 행·열 합 재검산", not g, "; ".join(g) if g else "")

    # J-12 § 상호참조 실존성
    valid = None
    if a.sections:
        valid = {l.strip().replace(" ", "") for l in open(a.sections, encoding="utf-8") if l.strip()}
    found, broken = section_refs(root, valid)
    if valid:
        check("J-12 § 상호참조 실존", not broken, f"깨진 참조 {broken}" if broken else f"{len(found)}종 전부 실존")
    else:
        print(f"  INFO  § 참조 {len(found)}종 검출 (--sections 미지정이라 실존성 미검증)")

    # J-13 필수 문자열 (규율 I 흡수 — 단, 단독 통과는 발급하지 않는다)
    if a.required:
        need = [l.rstrip("\n") for l in open(a.required, encoding="utf-8") if l.strip()]
        miss = [s for s in need if s not in raw]
        check("J-13 필수 문자열 실기재", not miss, f"누락 {len(miss)}건: {miss[:5]}" if miss else f"{len(need)}종 전량")

    # J-14 강조(굵기) 소실 — 본문 텍스트가 전량 보존돼도 서식만 사라질 수 있다
    ndef, napp, nsrc = emphasis_check(parts, a.md)
    if nsrc is None:
        print(f"  INFO  굵기 charPr 정의 {ndef}종 / 적용 run {napp}개 "
              f"(--md 미지정이라 원고 대조 없음)")
    elif nsrc == 0:
        print(f"  INFO  원고에 굵기 표기가 없어 검사 생략 (적용 run {napp}개)")
    elif ndef == 0:
        check("J-14 강조(굵기) 보존", False,
              f"원고 굵기 {nsrc}개인데 산출물 <hh:bold> 정의 0건 — 전량 소실")
    else:
        check("J-14 강조(굵기) 보존", napp >= nsrc * 0.5,
              f"원고 {nsrc}개 → 적용 run {napp}개 (정의 {ndef}종)")

    # J-15 절 제목 축자 대조 — 개명·접미추가·띄어쓰기 변형·절 신설을 잡는다
    if a.titles:
        want = [l.strip() for l in open(a.titles, encoding="utf-8") if l.strip()]
        body = re.sub(r"\s+", " ", "\n".join(
            local_text(p) for p in root.iter(f"{{{HP}}}p")))
        miss = [t for t in want if re.sub(r"\s+", " ", t) not in body]
        check("J-15 절 제목 축자 일치", not miss,
              f"불일치 {len(miss)}건: {miss[:4]}" if miss else f"{len(want)}종 전량 원문 일치")

    # J-16 용지 규격·방향 정합성 — 열어보기 전에는 드러나지 않는다
    wm, hm, ls, pbad = page_check(raw, a.paper)
    check(f"J-16 용지 규격·방향({a.paper})", not pbad,
          "; ".join(pbad) if pbad else
          f"{wm:.0f}×{hm:.0f}mm · {ls}")

    # J-17 표 폭 ↔ 본문 문단 폭 — 여백 패치 뒤 표를 다시 재단했는지 본다
    tw, twbad = table_width_check(raw)
    if tw is None:
        print("  INFO  hp:pagePr 미검출 — J-17 표 폭 대조 생략(구 파이프라인 산출물)")
    elif not shapes:
        print("  INFO  표 0개 — J-17 생략")
    else:
        check("J-17 표 폭 ↔ 본문 문단 폭", not twbad,
              "; ".join(twbad[:3]) + (f" 외 {len(twbad)-3}건" if len(twbad) > 3 else "")
              if twbad else f"표 {len(shapes)}개 전량 {tw} 일치 ({tw/283.465:.0f}mm)")

    ok = not fails
    print(f"\n{'='*60}\n{'PASS' if ok else 'FAIL'} — 실패 {len(fails)}건")
    for f in fails:
        print(f"  · {f}")
    print("\n※ 측정 매체: 전 항목 hwpx(산출물). md 단독 측정 항목은 이 게이트에 없다.")

    if a.json:
        json.dump({"pass": ok, "checks": res,
                   "tables": [{"idx": s[0], "rows": s[1], "cols": s[2], "first": s[3]} for s in shapes],
                   "fails": fails},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
