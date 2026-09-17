#!/usr/bin/env python3
"""규율 K — 양식 준수 게이트.

「양식을 지켰다」는 **선언이 아니라 측정 결과**다. 이 스크립트는 양식 명세(JSON)와
**HWPX 산출물**(구조 기준)·**조립용 원고**(목차 기준)를 대조해 다음을 기계로 확인한다.

  F-1 장·절 제목 축자 일치 + 순서            [매체: hwpx]
  F-2 절 신설·누락 0 (양식 목차와 집합 일치)   [매체: md]
  F-3 절별 요구 항목 커버리지                  [매체: hwpx, 절 단위 스코프]
  F-4 지정 서식 특수검사(표 A·표 B·KPI 5요소·가중치 100%·기술분류 3순위·핵심어 5개) [매체: hwpx]
  F-5 양식 설명문 잔존 0                       [매체: hwpx + md]
  F-6 표 열수 상한 / 표·그림 개수 상한          [매체: hwpx]
  F-7 산문 자수 상한(분량 예산 사전검사)        [매체: md]

★ 쪽수 실측은 이 게이트가 하지 않는다 — `gate_pages.py`(한컴 COM)가 담당한다.
  F-7 은 착수 전 예산 점검용 **추정**이며, 실측을 대체하지 않는다.

사용:
  python3 gate_form.py --hwpx 30_proposal.hwpx --md 30_proposal.build.md \
      --spec .../default_form_spec.json [--json gate_form.json]

종료코드 0=PASS, 1=FAIL, 2=실행 오류.
"""
import argparse, json, os, re, sys, zipfile
import xml.etree.ElementTree as ET

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
T, P, TBL, TR, TC, PIC = (f"{{{HP}}}{x}" for x in ("t", "p", "tbl", "tr", "tc", "pic"))


def norm(s):
    """공백·마크다운 강조·괄호 안 공백 차이를 흡수한 비교용 정규화."""
    s = re.sub(r"\*\*|__", "", s or "")
    return re.sub(r"\s+", "", s)


def local_text(p):
    """이 문단에 직접 속한 텍스트(하위 표 제외) — gate_hwpx.py 와 동일 규약."""
    out = []

    def walk(n):
        for ch in n:
            if ch.tag == TBL:
                continue
            if ch.tag == T:
                out.append(ch.text or "")
            walk(ch)

    walk(p)
    return "".join(out)


def cell_text(tc):
    return "".join(t.text or "" for t in tc.iter(T)).strip()


def harvest(tbl):
    """표 → 행렬(문자열 2차원)."""
    rows = []
    for tr in tbl.findall(TR):
        rows.append([cell_text(tc) for tc in tr.findall(TC)])
    return rows


class Doc:
    """HWPX 를 절 단위로 쪼갠 뷰. 표·그림은 소속 절에 귀속시킨다."""

    def __init__(self, path, titles):
        self.sections = {}       # id -> {"text": [...], "tables": [...], "pics": 0}
        self.order = []          # 등장 순서의 절 id
        self.title_of = {norm(t): i for i, t in titles}   # 정규화 제목 -> id
        self.cur = "_preamble"
        self._new(self.cur)
        zf = zipfile.ZipFile(path)
        self.parts = [n for n in zf.namelist() if n.startswith("Contents/section")]
        for name in sorted(self.parts):
            root = ET.fromstring(zf.read(name))
            self._walk(root)

    def _new(self, sid):
        if sid not in self.sections:
            self.sections[sid] = {"text": [], "tables": [], "pics": 0}
            self.order.append(sid)

    def _walk(self, node):
        for ch in node:
            if ch.tag == P:
                txt = local_text(ch)
                key = norm(txt)
                # 제목 문단은 제목만 담긴 문단이어야 한다(본문 중 언급과 구분)
                if key in self.title_of:
                    self.cur = self.title_of[key]
                    self._new(self.cur)
                self.sections[self.cur]["text"].append(txt)
                self._walk(ch)
            elif ch.tag == TBL:
                rows = harvest(ch)
                self.sections[self.cur]["tables"].append(rows)
                self.sections[self.cur]["text"].append(
                    " ".join(c for r in rows for c in r))
                # 표 내부로는 내려가지 않는다(셀 텍스트 이중 계상 방지)
            elif ch.tag == PIC:
                self.sections[self.cur]["pics"] += 1
                self._walk(ch)
            else:
                self._walk(ch)

    def text(self, sid):
        return " ".join(self.sections.get(sid, {}).get("text", []))

    def all_text(self):
        return " ".join(self.text(s) for s in self.order)

    def tables(self, sid):
        return self.sections.get(sid, {}).get("tables", [])


# ---------------- 특수검사 ----------------

def sp_class3(text):
    """기술분류 소분류 3순위·비중 합 100%."""
    m = [l for l in re.split(r"[|\n]", text) if re.search(r"기술\s*분류|분류", l) and "%" in l]
    if not m:
        return False, "기술분류 행에서 비중(%) 미검출"
    pcts = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", " ".join(m))]
    if len(pcts) < 3:
        return False, f"소분류 3순위 미달(비중 {len(pcts)}개)"
    tot = sum(pcts[:3])
    return abs(tot - 100) < 0.6, f"3순위 비중 합 {tot:g}%"


def sp_keywords5(text):
    seg = re.split(r"핵심어", text)
    if len(seg) < 2:
        return False, "핵심어 항목 없음"
    tail = seg[1][:400]
    ko = re.search(r"\(국문\)(.*?)(?:\(영문\)|$)", tail, re.S)
    en = re.search(r"\(영문\)(.*)", tail, re.S)
    def cnt(s):
        return len([x for x in re.split(r"[,/·;]", s) if x.strip()])
    if ko and en:
        nk, ne = cnt(ko.group(1)), cnt(en.group(1)[:200])
        return (nk <= 5 and ne <= 5), f"국문 {nk}개 / 영문 {ne}개 (각 5개 이내)"
    n = cnt(tail.split("|")[0])
    return n <= 5, f"{n}개 (5개 이내)"


def sp_table_a(tables):
    for rows in tables:
        if not rows:
            continue
        head = norm(" ".join(rows[0]))
        if len(rows[0]) == 3 and "구분" in head and "연차" in head and "목표" in head:
            return True, f"[표 A] 3열 {len(rows)}행"
    shapes = [f"{len(r)}행×{len(r[0]) if r else 0}열" for r in tables]
    return False, f"열 구성 `구분/연차/목표` 3열 표 없음 (실측 {shapes})"


def sp_table_b(tables):
    for rows in tables:
        if not rows:
            continue
        head = " ".join(rows[0])
        months = len(re.findall(r"\b(?:1[0-2]|[1-9])\b", head))
        if len(rows[0]) >= 13 and months >= 12:
            return True, f"[표 B] {len(rows[0])}열(월 12칸) {len(rows)}행"
    shapes = [f"{len(r)}행×{len(r[0]) if r else 0}열" for r in tables]
    return False, f"월 단위 12칸 간트표 없음 (실측 {shapes})"


KPI5 = ["단위", "기준값", "목표치", "평가방법", "평가환경"]


def sp_kpi5(tables, text):
    """양식 요구 5요소(단위·기준값·목표치·평가방법·평가환경)를 **KPI 표의 열**에서 확인한다.

    ★ 실측(2026-08-15): 종전 구현은 「절 안 어디든 그 단어가 있으면 통과」였다. 그래서
      평가방법·평가환경을 표 밖 산문으로 뭉뚱그린 판이 **전부 통과**했다 — 어느 지표의 방법인지
      대응이 안 되는데도. 규율 I(「존재 검사 단독은 거짓 통과를 발급한다」)의 네 번째 재발이다.
      → 지표별 1:1 대응을 강제하려면 **표의 열**로 봐야 한다.
    """
    kpi = None
    for rows in tables:
        if not rows:
            continue
        h = norm(" ".join(rows[0]))
        if "가중치" in h and ("성과지표" in h or "지표" in h):
            kpi = rows
            break
    if kpi is None:
        heads = norm(" ".join(" ".join(r[0]) for r in tables if r))
        miss = [k for k in KPI5 if k not in heads and k not in norm(text)]
        return (not miss), (f"KPI 표 미검출 — 절 텍스트로만 확인{'' if not miss else f' · 누락 {miss}'}")
    head = norm(" ".join(kpi[0]))
    miss = [k for k in KPI5 if k not in head]
    if not miss:
        return True, f"5요소 전량이 표의 열 ({len(kpi[0])}열)"
    intext = [k for k in miss if k in norm(text)]
    return False, (f"표의 열에 없음: {miss}"
                   + (f" (표 밖 산문에는 있으나 지표별 1:1 대응 불가: {intext})" if intext else ""))


SUM_ROW = re.compile(r"\s*(계|합계|총계|소계)\s*")


def sp_weight100(tables):
    """가중치 열의 합이 100% 인지. ★ 합계 행을 함께 더하면 200% 가 나와 거짓 FAIL 한다 —
    첫 두 칸 중 첫 비어있지 않은 칸이 「계/합계/총계/소계」인 행은 제외한다."""
    for rows in tables:
        if len(rows) < 2:
            continue
        ncol = max(len(r) for r in rows)
        body = [r for r in rows[1:]
                if not SUM_ROW.fullmatch(next((c for c in r[:2] if c.strip()), ""))]
        for c in range(ncol):
            vals = []
            for r in body:
                if c < len(r):
                    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*%?\s*", r[c])
                    if m:
                        vals.append(float(m.group(1)))
            if len(vals) >= 3 and abs(sum(vals) - 100) < 0.6:
                return True, f"가중치 열 합 100% ({len(vals)}개 항목)"
    return False, "합이 100%인 가중치 열을 찾지 못함"


def sp_table_c(tables):
    """[표 C] 연차별 연구내용 — 열 `연차/내용/방법/근거` 4열."""
    for rows in tables:
        if not rows:
            continue
        head = norm(" ".join(rows[0]))
        if len(rows[0]) >= 4 and "연차" in head and "내용" in head and "방법" in head:
            return True, f"[표 C] {len(rows[0])}열 {len(rows)}행"
    shapes = [f"{len(r)}행×{len(r[0]) if r else 0}열" for r in tables]
    return False, f"연차/내용/방법/근거 4열 표 없음 (실측 {shapes})"


LEDGER_KEY = re.compile(r"[A-Z]{3,4}_[A-Z0-9_]{2,}")


def ledger_sources(ws):
    """워크스페이스의 조사 산출물에서 「확정 수치 대장」의 **출처 열**을 읽어 식별 토큰 사전을 만든다.

    대장 스키마: `| key | 값 | 단위 | 기준연도 | 출처(계층) | 확신도 |`
    반환: 출처 문자열에서 뽑은 토큰 집합(기관·문서·번호 — 예 NIST, arXiv, 2509.19588, KISTEP).
    """
    toks = set()
    if not ws or not os.path.isdir(ws):
        return toks
    for fn in sorted(os.listdir(ws)):
        if not fn.endswith(".md"):
            continue
        try:
            txt = open(os.path.join(ws, fn), encoding="utf-8").read()
        except Exception:
            continue
        grab = False
        for line in txt.split("\n"):
            if re.match(r"^#{1,4}\s*.*확정\s*\S*\s*대장", line):
                grab = True
                continue
            if grab and re.match(r"^#{1,4}\s", line):
                grab = False
            if not (grab and line.strip().startswith("|")):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 5:
                continue
            for t in re.findall(r"[A-Za-z][A-Za-z0-9.\-]{2,}|[가-힣]{2,}", cells[4]):
                if not LEDGER_KEY.fullmatch(t):
                    toks.add(t)
    return toks


def sp_table_c_ledger(tables, spec, ws=None):
    """F-12 — 연차별 연구내용 표의 `근거` 열은 **대장이 지정한 출처명**, 셀은 자수 상한 이내.

    ★ 실측(2026-08-15, c1↔c2): 같은 근거팩을 동결해 줬는데도 이 열이 한쪽은 특허공보·물성
      라이브러리, 다른 쪽은 arXiv·업계지로 갈렸다. 근거 개체 일치도가 0.67 에 묶인 주범이고,
      결론 일치도(L6)를 깎는 7행 중 4행이 이 표였다. **무엇을 인용할지 자유로우면 갈린다.**
    ★★ 그래서 처음에는 「대장 key 를 적어라」로 고정했는데 **그게 더 나빴다**(실측 2026-08-15, c3):
      게이트는 통과했지만 심사자가 읽는 표의 근거 열에 `TECH_SOTA_METRIC`·`PAT_WHITE_SPACE` 같은
      **내부 변수명이 그대로 인쇄**됐다. 인용을 고정하는 것과 내부 식별자를 인쇄하는 것은 다른 문제다.
      → 지금은 **대장의 「출처」 열에 실재하는 표기**를 요구하고, key 원문은 **금칙**으로 잡는다.
      워크스페이스를 주면(`--ledger`) 대장과 대조하고, 없으면 금칙·자수만 보고 그 사실을 밝힌다.
    """
    lim = int((spec.get("limits") or {}).get("table_cell_chars") or 0)
    src = ledger_sources(ws)
    for rows in tables:
        if not rows or len(rows[0]) < 4:
            continue
        head = norm(" ".join(rows[0]))
        if not ("연차" in head and "내용" in head and "방법" in head):
            continue
        body = rows[1:]
        if not body:
            return False, "연차별 연구내용 표: 본문 행 없음"
        det = []
        leaked = [r[0] for r in body if LEDGER_KEY.search(r[-1])]
        if leaked:
            det.append("근거 열에 대장 key 원문이 인쇄됨(출처명으로 바꿀 것): " + ", ".join(leaked[:4]))
        empty = [r[0] for r in body if len(r[-1].strip()) < 4]
        if empty:
            det.append("근거 열이 비었거나 너무 짧음: " + ", ".join(empty[:4]))
        unknown = []
        if src:
            for r in body:
                cell = r[-1]
                if not any(t in cell for t in src):
                    unknown.append(r[0])
            if unknown:
                det.append("대장 출처에 없는 근거: " + ", ".join(unknown[:4]))
        over = [(r[0], len(c)) for r in body for c in r if lim and len(c) > lim]
        if over:
            det.append(f"셀 자수 초과({lim}자): " + ", ".join(f"{n} {L}자" for n, L in over[:4]))
        tail = (f"근거 열 {len(body)}행 대장 출처와 일치 · 셀 {lim}자 이내"
                if src else f"근거 열 {len(body)}행 — key 원문 0건·셀 {lim}자 이내 (대장 대조 미실시: --ledger 미지정)")
        return (not det), ("; ".join(det) if det else tail)
    return True, "연차별 연구내용 표 없음 — TABLE_C 검사에서 이미 잡힌다"


def sp_fig_or_table(doc, sid):
    s = doc.sections.get(sid, {})
    n_t, n_p = len(s.get("tables", [])), s.get("pics", 0)
    return (n_t + n_p) > 0, f"표 {n_t}개 · 그림 {n_p}장"


def blueprint_check(md_text, spec):
    """F-11 골격 준수 — □ 리드·ㅇ 슬롯의 **문구·순서·개수**를 명세와 축자 대조.

    ★ 실측(2026-08-15): 골격을 지시로만 주면 실행마다 항목이 늘거나 준다(□ 43/34/37).
      구조가 갈리면 같은 근거로 써도 유사도가 0.7 대에 머문다. **게이트가 잡아야 지켜진다.**
    측정 매체는 **조립용 원고(md)** 다 — 조판 뒤에는 말머리가 기호로 바뀌어 문구 대조가 어렵다.
    """
    want_leads, want_slots = [], []
    for n in spec.get("outline", []):
        for b in (n.get("blueprint") or []):
            if isinstance(b, str):
                want_leads.append(b)
                continue
            want_leads.append(b["lead"])
            want_slots += [sl["text"] for sl in b.get("slots", [])]
    if not want_leads:
        return None

    def norm_line(x):
        # [PATCH 2026-09-07] 구분자에 의존하지 않게 한다.
        #   원본은 em-dash 로만 잘라 라벨을 내는데, 연구계획서 개조식에
        #   em-dash 를 쓰지 않아 `:` 로 바꾸자 **슬롯 64개가 전부 「초과」로 잡혔다.**
        #   게이트가 보려는 것은 **라벨**이지 구두점이 아니다.
        return re.split(r"[—:：]",
                        re.sub(r"\s+", "", re.sub(r"\*\*|`", "", x)))[0]

    got_leads = [norm_line(m.group(1)) for m in re.finditer(r"^- (.+)$", md_text, re.M)]
    got_slots = [norm_line(m.group(1)) for m in re.finditer(r"^  - (.+)$", md_text, re.M)]
    wl = [norm_line(x) for x in want_leads]
    ws = [norm_line(x) for x in want_slots]
    miss_l = [want_leads[i] for i, x in enumerate(wl) if x not in got_leads]
    miss_s = [want_slots[i] for i, x in enumerate(ws) if x not in got_slots]
    extra_l = [x for x in got_leads if x not in wl]
    extra_s = [x for x in got_slots if x not in ws]
    return {"want_l": len(wl), "want_s": len(ws), "got_l": len(got_leads), "got_s": len(got_slots),
            "miss_l": miss_l, "miss_s": miss_s, "extra_l": extra_l, "extra_s": extra_s}


def typography_check(path, spec):
    """F-9·F-10 글자 크기·굵기 규율.

    양식이 정한 크기는 **본문 11 / 절 13 / 장 16 / 표 9pt** 다. 조립 도구는 이를 지키지 않는다 —
    실측에서 목록 글자가 **11.73pt** 로 108회 나갔고 표는 8.8pt 였다(둘 다 눈으로는 안 보인다).
    굵기도 마찬가지다. 개조식 항목마다 굵은 리드를 달면 **강조가 강조로 안 보인다** — 제목·표 라벨만 남긴다.

    ★ 제목 스타일은 하드코딩하지 않고 **제목 문단에만 쓰이는 charPr** 을 산출물에서 찾아 판별한다.
    """
    style = (spec or {}).get("style") or {}
    body_pt = float(style.get("body_pt", 11))
    tbl_pt = float(style.get("table_pt", 9))
    h2_pt = float(style.get("chapter_title_pt", 16))
    h3_pt = float(style.get("section_title_pt", 13))
    tol = float(style.get("size_tolerance_pt", 0.3))

    zf = zipfile.ZipFile(path)
    head = zf.read("Contents/header.xml").decode("utf-8")
    sizes, bolds = {}, {}
    for m in re.finditer(r'<hh:charPr id="(\d+)"(.*?)</hh:charPr>', head, re.S):
        cid, blk = m.group(1), m.group(2)
        hm = re.search(r'height="(\d+)"', blk)
        sizes[cid] = int(hm.group(1)) / 100 if hm else None
        bolds[cid] = "<hh:bold" in blk

    sec = "".join(zf.read(n).decode("utf-8")
                  for n in sorted(zf.namelist()) if n.startswith("Contents/section"))
    spans = [(m.start(), m.end()) for m in re.finditer(r"<hp:tbl\b.*?</hp:tbl>", sec, re.S)]
    in_tbl = lambda pos: any(a <= pos < b for a, b in spans)

    # 제목 전용 charPr 판별
    h2c, h3c, bodyc = set(), set(), set()
    for para in re.findall(r"<hp:p\b.*?</hp:p>", sec, re.S):
        cr = re.search(r'charPrIDRef="(\d+)"', para)
        if not cr:
            continue
        t = "".join(re.findall(r"<hp:t>([^<]*)</hp:t>", para)).strip()
        (h2c if re.match(r"^\d+\.\s", t) else h3c if re.match(r"^\d+-\d+\.\s", t) else bodyc).add(cr.group(1))
    h2c -= bodyc
    h3c -= bodyc

    # 본문은 문단 단위로 본다 — 캡션·표주석(※·그림·표)은 작은 글씨가 관행이라 예외다
    cap_pt = float(style.get("caption_pt", tbl_pt))
    body_bad, tbl_bad, n_body, n_bold = [], [], 0, 0
    first_tbl = spans[0] if spans else None
    for m in re.finditer(r"<hp:p\b.*?</hp:p>", sec, re.S):
        para, pos = m.group(0), m.start()
        cr = re.search(r'charPrIDRef="(\d+)"', para)
        if not cr:
            continue
        cid = cr.group(1)
        pt = sizes.get(cid)
        if pt is None or pt <= 2:          # 1pt 자리표시(빈 셀)는 무시
            continue
        text = "".join(re.findall(r"<hp:t>([^<]*)</hp:t>", para)).strip()
        if in_tbl(pos):
            # 표지 박스(첫 표)는 조립 도구가 만든 제목 상자라 검사 대상이 아니다
            if first_tbl and first_tbl[0] <= pos < first_tbl[1]:
                continue
            if abs(pt - tbl_pt) > tol:
                tbl_bad.append(pt)
            continue
        want = h2_pt if cid in h2c else h3_pt if cid in h3c else body_pt
        is_caption = text.startswith(("※", "그림", "표 ", "[표", "[그림"))
        if abs(pt - want) > tol and not (is_caption and abs(pt - cap_pt) <= tol):
            body_bad.append((pt, want))
        if cid not in h2c and cid not in h3c:
            n_body += 1
            n_bold += 1 if bolds.get(cid) else 0
    return {
        "body_bad": body_bad, "tbl_bad": tbl_bad,
        "bold_ratio": (n_bold / n_body) if n_body else 0.0,
        "n_body": n_body, "n_bold": n_bold,
        "spec": f"본문 {body_pt:g} / 절 {h3_pt:g} / 장 {h2_pt:g} / 표 {tbl_pt:g}pt",
    }


def style_check(doc, spec):
    """F-8 개조식 준수 — 본문 문단이 「말머리 + 명사형 종결」인지 본다.

    측정 매체는 **hwpx 본문 문단**(표 셀·제목·캡션 제외)이다. md 로 재면 목록 마커가
    조판 단계에서 어떻게 바뀌는지 못 보고, 표 안의 서술체를 본문으로 착각한다.

    ★ 함정: 「~다.」로 끝나면 서술체지만, **「~한다」로 끝나는 표제어**(예: 「…를 우선 탐색한다」)와
      숫자·단위로 끝나는 항목(「…88% 상승」)을 구분해야 한다. 종결 판정은 문단의 **마지막 어절**로만 한다.
    """
    ws = spec.get("writing_style")
    if not ws:
        return None
    markers = tuple(ws.get("markers", {}).values()) + ("○", "-", "·")
    exempt = tuple(ws.get("exempt_paragraph_prefixes", []))
    bad_end = tuple(ws.get("forbidden_endings", []))
    maxlen = int(ws.get("max_item_chars", 160))

    body, bullets, narrative, longs = [], [], [], []
    for sid in doc.order:
        for txt in doc.sections.get(sid, {}).get("text", []):
            t = (txt or "").strip()
            if len(t) < 12 or t.startswith(exempt):
                continue
            if norm(t) in doc.title_of:          # 장·절 제목
                continue
            body.append(t)
            if t.startswith(markers):
                bullets.append(t)
                if len(t) > maxlen:
                    longs.append(t[:28] + "…")
            last = re.sub(r"[)\]\s.]+$", "", t.split()[-1]) if t.split() else ""
            if any(last.endswith(e) for e in bad_end):
                narrative.append(t[:28] + "…")
    if not body:
        return None
    return {
        "n_body": len(body),
        "bullet_ratio": len(bullets) / len(body),
        "narrative": narrative,
        "narrative_ratio": len(narrative) / len(body),
        "longs": longs,
        "bullets": bullets,          # [PATCH 2026-09-14] F-8d 슬롯 길이용
    }


# ---------------- 본체 ----------------

def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # [PATCH] cp949 콘솔 크래시 방지
    ap = argparse.ArgumentParser()
    ap.add_argument("--hwpx", required=True)
    ap.add_argument("--md", help="조립용 원고(.build.md) — F-2·F-7 측정 매체")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--ledger", help="워크스페이스 경로 — 조사 산출물의 「확정 수치 대장」 출처와 대조(F-12)")
    ap.add_argument("--json")
    a = ap.parse_args()

    spec = json.load(open(a.spec, encoding="utf-8"))
    outline = spec["outline"]
    titles = [(n["id"], n["title"]) for n in outline]
    doc = Doc(a.hwpx, titles)
    md = open(a.md, encoding="utf-8").read() if a.md else None

    results, fails, warns = [], [], []

    def check(name, ok, detail, medium, severity="fail"):
        """severity='warn' 이면 양식이 「권장」으로 쓴 항목 — 기록은 남기되 통과를 막지 않는다."""
        tag = "OK " if ok else ("WARN" if severity == "warn" else "FAIL")
        results.append({"name": name, "ok": bool(ok), "detail": detail,
                        "medium": medium, "severity": severity})
        print(f"[{tag}] {name}  ({medium})  {detail}")
        if not ok:
            (warns if severity == "warn" else fails).append(name)

    # F-1 제목 축자 일치 + 순서 -------------------------------------------------
    found = [sid for sid in doc.order if sid != "_preamble"]
    want = [sid for sid, _ in titles]
    miss = [t for i, t in titles if i not in found]
    check("F-1 제목 축자 일치", not miss,
          f"{len(want)}개 중 {len(want)-len(miss)}개 일치" + (f" · 불일치/누락 {miss}" if miss else ""),
          "hwpx")
    seq_ok = [s for s in found if s in want] == [s for s in want if s in found]
    check("F-1b 목차 순서", seq_ok,
          "양식 순서와 동일" if seq_ok else f"순서 어긋남: {found}", "hwpx")

    # F-2 절 신설·누락 0 --------------------------------------------------------
    if md:
        heads = re.findall(r"^(#{2,3})\s+(.+?)\s*$", md, re.M)
        got = [norm(h[1]) for h in heads]
        want_n = [norm(t) for _, t in titles]
        extra = [h for h in got if h not in want_n]
        lack = [t for (_, t), n in zip(titles, want_n) if n not in got]
        check("F-2 절 신설·누락 0", not extra and not lack,
              ("양식 목차와 집합 일치" if not extra and not lack
               else f"신설 {len(extra)}건 {extra[:3]} · 누락 {len(lack)}건 {[l[:20] for l in lack[:3]]}"),
              "md")

    # F-3 절별 요구 항목 커버리지 -----------------------------------------------
    gaps = []
    for n in outline:
        stext = doc.text(n["id"])
        for pr in n.get("probes") or []:
            if not re.search(pr["regex"], stext):
                gaps.append(f"{n['id']}:{pr['key']}")
    total_probe = sum(len(n.get("probes") or []) for n in outline)
    check("F-3 요구 항목 커버리지", not gaps,
          f"{total_probe}개 중 {total_probe-len(gaps)}개 충족" + (f" · 미충족 {gaps}" if gaps else ""),
          "hwpx(절 단위)")

    # F-4 지정 서식 특수검사 -----------------------------------------------------
    for n in outline:
        for entry in n.get("special") or []:
            sid = n["id"]
            sp = entry["key"] if isinstance(entry, dict) else entry
            sev = entry.get("severity", "fail") if isinstance(entry, dict) else "fail"
            tb, tx = doc.tables(sid), doc.text(sid)
            if sp == "CLASS3":
                ok, d = sp_class3(tx)
            elif sp == "KEYWORDS5":
                # ★ 실측: 본문 리드에 「핵심어」가 들어가면 그 문장을 세어 **거짓 통과**가 났다.
                #   핵심어는 0장 요약표의 항목이므로 **표 셀에서 먼저** 찾는다.
                tbl_text = " ".join(c for rows in tb for r in rows for c in r)
                ok, d = sp_keywords5(tbl_text if "핵심어" in tbl_text else tx)
            elif sp == "TABLE_A":
                ok, d = sp_table_a(tb)
            elif sp == "TABLE_C":
                ok, d = sp_table_c(tb)
            elif sp == "TABLE_C_LEDGER":
                ok, d = sp_table_c_ledger(tb, spec, a.ledger)
            elif sp == "TABLE_B":
                ok, d = sp_table_b(tb)
            elif sp == "KPI5":
                ok, d = sp_kpi5(tb, tx)
            elif sp == "WEIGHT100":
                ok, d = sp_weight100(tb)
            elif sp == "FIG_OR_TABLE":
                ok, d = sp_fig_or_table(doc, sid)
            else:
                ok, d = False, f"미지원 특수검사 {sp}"
            check(f"F-4 {sid} {sp}", ok, d, "hwpx", sev)

    # F-5 설명문 잔존 0 ----------------------------------------------------------
    body = doc.all_text()
    res_hits = []
    for pat in spec.get("guide_residue_patterns", []):
        if re.search(pat, body):
            res_hits.append(pat)
    flat = norm(body)
    # 양식이 「본문에 그대로 쓰라」고 준 표제(가./나./다./라., [표 A] 등)는 잔존이 아니다
    exempt = [norm(e) for e in spec.get("residue_exempt", [])]
    for g in [x for n in outline for x in (n.get("guide") or [])]:
        probe = norm(g.split(":")[-1])
        if any(e in probe for e in exempt):
            continue
        if len(probe) >= 12 and probe in flat:
            res_hits.append(g[:36])
    check("F-5 양식 설명문 잔존 0", not res_hits,
          "잔존 0건" if not res_hits else f"{len(res_hits)}건 {res_hits[:3]}", "hwpx")
    if md:
        md_hits = [p for p in ("<!--", "FORM-GUIDE") if p in md]
        check("F-5b 가이드 주석 잔존 0", not md_hits,
              "0건" if not md_hits else f"{md_hits} — form_strip.py 를 돌리지 않았다", "md")

    # F-13 내부 식별자 잔존 0 ------------------------------------------------------
    # ★ 실측(2026-08-15, 3회 실행): 대장 key(`TECH_SOTA_METRIC`)·축 이름(`(축 A 판정)`)·
    #   `확정 수치 대장` 이 **출처 자리**에 인쇄됐다. 심사자에게는 아무 의미가 없는 문자열이며,
    #   근거를 밝혀야 할 칸을 자기 참조가 차지한 상태다. 게이트 어느 항목도 이걸 보지 않았다.
    jar = []
    for pat in spec.get("internal_jargon_patterns", []):
        for m in re.finditer(pat, body):
            jar.append(m.group(0))
    if spec.get("internal_jargon_patterns"):
        uniq = sorted(set(jar))
        check("F-13 내부 식별자 잔존 0", not jar,
              "0건" if not jar else f"{len(jar)}건 {uniq[:5]} — 대장 key 는 내부 포인터다. 문서에는 그 key 가 가리키는 **출처명**을 쓴다",
              "hwpx")

    # F-6 표·그림 상한 -----------------------------------------------------------
    lim = spec.get("limits", {})
    all_tbl = [t for sid in doc.order for t in doc.tables(sid)]
    # 양식이 열 수를 지정한 절([표 B] 간트 13열 등)은 열수 상한에서 제외한다
    exempt = set(lim.get("table_cols_exempt_sections", []))
    wide = [f"{sid}:{len(t)}행×{max(len(r) for r in t)}열"
            for sid in doc.order if sid not in exempt
            for t in doc.tables(sid)
            if t and max(len(r) for r in t) > lim.get("table_cols_max", 6)]
    check("F-6a 표 열수 상한", not wide,
          f"열수 초과 {len(wide)}개 {wide[:4]}" if wide else
          f"전 표 {lim.get('table_cols_max',6)}열 이하 (표 {len(all_tbl)}개"
          + (f", 양식 지정 절 {sorted(exempt)} 제외)" if exempt else ")"), "hwpx")
    npic = sum(doc.sections[s]["pics"] for s in doc.order)
    # 프리셋 표지 박스가 표 1개로 잡히므로 상한 비교는 +1 을 허용한다
    check("F-6b 표·그림 개수", len(all_tbl) <= lim.get("tables", 5) + 1 and npic <= lim.get("figures", 1),
          f"표 {len(all_tbl)}개(상한 {lim.get('tables',5)}+표지1) · 그림 {npic}장(상한 {lim.get('figures',1)})",
          "hwpx")

    # F-7 산문 자수(분량 예산 사전검사) -------------------------------------------
    if md:
        prose = re.sub(r"\s+", "", re.sub(r"^\|.*$", "", md, flags=re.M))
        n = len(prose)
        check("F-7 산문 자수 상한", n <= lim.get("prose_chars", 15000),
              f"{n:,}자 (상한 {lim.get('prose_chars',15000):,}자) — 추정치, 쪽수 실측은 gate_pages.py", "md")

    # F-8 개조식 준수 -----------------------------------------------------------
    ws = spec.get("writing_style") or {}
    st = style_check(doc, spec)
    if st:
        rmin = float(ws.get("bullet_ratio_min", 0.8))
        nmax = float(ws.get("narrative_ratio_max", 0.10))
        check(f"F-8a 개조식 말머리 비율(≥{rmin:.0%})", st["bullet_ratio"] >= rmin,
              f"본문 {st['n_body']}문단 중 말머리 {st['bullet_ratio']:.0%}", "hwpx")
        check(f"F-8b 서술형 종결(≤{nmax:.0%})", st["narrative_ratio"] <= nmax,
              f"{len(st['narrative'])}건 {st['narrative'][:3]}" if st["narrative"] else "0건",
              "hwpx")
        check(f"F-8c 항목 길이(≤{ws.get('max_item_chars',160)}자)", not st["longs"],
              f"초과 {len(st['longs'])}건 {st['longs'][:3]}" if st["longs"] else "전 항목 이내",
              "hwpx", "warn")

        # [PATCH 2026-09-14] F-8d 슬롯 길이 — **실패**로 잡는다.
        #   명세에 `slot_max_chars: 115` 가 있는데 **게이트가 한 번도 안 봤다.**
        #   실측: 슬롯 64개 평균 155자 · 최대 167 — 한 줄이 40자이니 평균 네 줄이다.
        #   사용자 요건은 「한 bullet 당 한 줄, 길어야 두 줄」이다.
        #   짧게 쓰라는 게 아니라 **사실 하나에 슬롯 하나**를 쓰라는 뜻이다.
        smax = int(ws.get("slot_max_chars", 115))
        slots = [t for t in st["bullets"] if t.startswith(("○", "-", "·"))]
        over = [t[:40] + "…" for t in slots if len(t) > smax]
        check(f"F-8d 슬롯 길이(≤{smax}자)", not over,
              (f"초과 {len(over)}/{len(slots)}건 {over[:2]}" if over
               else f"슬롯 {len(slots)}건 전량 준수"),
              "hwpx")

    # F-11 골격 준수 ------------------------------------------------------------
    if md:
        bpc = blueprint_check(md, spec)
        if bpc:
            tol = int(((spec.get("writing_style") or {}).get("blueprint_extra_tolerance", 2)))
            # [PATCH 2026-09-14] 슬롯은 **개수·문구를 고정하지 않는다.**
            #
            #   원래 F-11 은 리드·슬롯을 **축자 대조**했다. 실행마다 항목이 늘거나
            #   주는 것을 막으려는 것이었고, 그 목적은 옳았다.
            #
            #   그런데 사용자 요건이 바뀌었다 — 「한 bullet 당 한 줄, 길어야 두 줄」.
            #   한 슬롯에 서너 사실을 몰아넣던 것을 **사실 하나에 슬롯 하나**로 쪼개면
            #   슬롯 수가 늘고 문구가 달라진다(실측: 64개 155자 → 247개 32.6자).
            #   축자 대조로는 **원리적으로 통과할 수 없다.**
            #
            #   그래서 기준을 바꾼다.
            #     리드   = 문서의 뼈대다. 그대로 **축자 대조**한다(누락·초과 모두 본다)
            #     슬롯   = 내용의 알갱이다. **최소 개수만** 본다(명세의 슬롯 수 이상)
            #
            #   슬롯이 줄면 내용이 빠진 것이므로 여전히 잡힌다.
            #   늘어나는 것은 쪼갠 결과이므로 통과시킨다.
            slot_min = len(bpc["ws_list"]) if "ws_list" in bpc else bpc["want_s"]
            slot_short = bpc["got_s"] < slot_min
            bad = (bpc["miss_l"] or len(bpc["extra_l"]) > tol or slot_short)
            check("F-11 골격(리드 축자 · 슬롯 최소)", not bad,
                  (f"리드 {bpc['got_l']}/{bpc['want_l']} · 슬롯 {bpc['got_s']}/≥{slot_min}"
                   + (f" · 누락 리드 {bpc['miss_l'][:2]}" if bpc["miss_l"] else "")
                   + (f" · 초과 리드 {len(bpc['extra_l'])}개 {bpc['extra_l'][:2]}"
                      if len(bpc["extra_l"]) > tol else "")
                   + (" · ★슬롯 부족" if slot_short else "")),
                  "md")

    # F-9·F-10 글자 크기·굵기 -------------------------------------------------
    tg = typography_check(a.hwpx, spec)
    bad = len(tg["body_bad"]) + len(tg["tbl_bad"])
    check("F-9 글자 크기 규율", not bad,
          (f"규격 외 {bad}건 — 본문 {sorted({p for p, _ in tg['body_bad']})} · "
           f"표 {sorted(set(tg['tbl_bad']))}") if bad else f"{tg['spec']} 전량 준수",
          "hwpx")
    bmax = float((spec.get("style") or {}).get("bold_ratio_max", 0.05))
    check(f"F-10 본문 굵기 절제(≤{bmax:.0%})", tg["bold_ratio"] <= bmax,
          f"본문 {tg['n_body']} run 중 굵기 {tg['n_bold']} ({tg['bold_ratio']:.0%}) — 제목·표 라벨 제외",
          "hwpx", "warn")

    ok = not fails
    print(f"\n{'='*60}\n{'PASS' if ok else 'FAIL'} — 실패 {len(fails)}건"
          + (f" · 경고 {len(warns)}건" if warns else ""))
    for f in fails:
        print(f"  - {f}")
    for w in warns:
        print(f"  ~ (권장) {w}")
    if a.json:
        json.dump({"pass": ok, "fails": fails, "warns": warns, "checks": results},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"결과 JSON: {a.json}")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"실행 오류: {e}")
        sys.exit(2)
