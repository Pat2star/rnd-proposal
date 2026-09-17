# -*- coding: utf-8 -*-
"""HWPX 검증기 L0~L5.

    PYTHONPATH=$CLAUDE_PLUGIN_ROOT python -m engine.hwpx.validate_hwpx --file out.hwpx --form forms/strategic-2027 \\
        --level 5 --json report.json

exit: 0 통과 / 1 경고만 / 2 오류

L0 ZIP 구조    L1 XML well-formed    L2 참조 무결성 ★    L3 기하 불변식
L4 양식 준수 (header.xml sha256 바이트 동일) ★    L5 한컴 실렌더
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile

from lxml import etree

from . import profile as profmod
from .consts import NS, MIMETYPE


def _added_ids(orig: bytes, new: bytes) -> list[str]:
    """덧붙인 항목을 「종류 id」로. 전에는 borderFill 만 셌다(2026-09-17 확장)."""
    from .header_extend import GROUPS
    out = []
    for _, item in GROUPS:
        pat = rf'<hh:{item} id="(\d+)"'
        a = set(re.findall(pat, orig.decode("utf-8")))
        b = set(re.findall(pat, new.decode("utf-8")))
        out += [f"{item} {i}" for i in sorted(b - a, key=int)]
    return out


def _kill_hwp():
    """멈춘 한글 프로세스 정리. 대화상자에 걸리면 스스로 안 죽는다."""
    import subprocess
    try:
        subprocess.run(["taskkill", "/F", "/IM", "Hwp.exe"],
                       capture_output=True, timeout=15)
    except Exception:                                       # noqa: BLE001
        pass


class Result:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: dict = {}

    def err(self, level, msg):
        self.errors.append(f"[L{level}] {msg}")

    def warn(self, level, msg):
        self.warnings.append(f"[L{level}] {msg}")

    @property
    def code(self) -> int:
        return 2 if self.errors else (1 if self.warnings else 0)


def _l0(z: zipfile.ZipFile, tmpl: str, r: Result):
    names = z.namelist()
    if not names or names[0] != "mimetype":
        r.err(0, f"mimetype이 0번째 엔트리가 아니다 (실제: {names[:1]})")
    else:
        if z.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
            r.err(0, "mimetype이 STORED가 아니다")
        if z.read("mimetype").decode(errors="replace") != MIMETYPE:
            r.err(0, "mimetype 내용이 application/hwp+zip이 아니다")
    need = ["Contents/header.xml", "Contents/section0.xml",
            "Contents/content.hpf", "settings.xml", "META-INF/container.xml"]
    for n in need:
        if n not in names:
            r.err(0, f"필수 엔트리 누락: {n}")
    if tmpl and os.path.exists(tmpl):
        with zipfile.ZipFile(tmpl) as t:
            missing = set(t.namelist()) - set(names)
        if missing:
            r.err(0, f"원본 대비 엔트리 누락 {len(missing)}건: {sorted(missing)[:5]}")
    r.info["entries"] = len(names)


def _l1(z: zipfile.ZipFile, r: Result) -> dict:
    trees = {}
    for n in z.namelist():
        if not n.endswith((".xml", ".hpf", ".rdf")):
            continue
        try:
            trees[n] = etree.fromstring(z.read(n))
        except Exception as e:                              # noqa: BLE001
            r.err(1, f"{n} 파싱 실패: {e}")
    return trees


def _collect_ids(header) -> dict[str, set]:
    g = lambda tag: {e.get("id") for e in header.iter("{%s}%s" % (NS['hh'], tag))}
    return {"paraPr": g("paraPr"), "charPr": g("charPr"), "style": g("style"),
            "borderFill": g("borderFill"), "tabPr": g("tabPr"),
            "bullet": g("bullet"), "numbering": g("numbering")}


def _l2(z, trees, r: Result):
    header = trees.get("Contents/header.xml")
    section = trees.get("Contents/section0.xml")
    hpf = trees.get("Contents/content.hpf")
    if header is None or section is None:
        r.err(2, "header.xml 또는 section0.xml을 파싱하지 못해 참조 검사를 못 한다")
        return
    ids = _collect_ids(header)

    checks = [("paraPrIDRef", "paraPr"), ("charPrIDRef", "charPr"),
              ("styleIDRef", "style"), ("borderFillIDRef", "borderFill"),
              ("tabPrIDRef", "tabPr")]
    bad = []
    for el in section.iter():
        for attr, kind in checks:
            v = el.get(attr)
            if v is not None and v not in ids[kind]:
                bad.append(f"{etree.QName(el).localname}@{attr}={v} ({kind}에 없음)")
    # heading.idRef → bullet 또는 numbering
    # ★ idRef="0"은 '없음'을 뜻한다. 원본 header.xml 자체가 OUTLINE idRef="0"을
    #   쓰면서 numberings에는 id=1만 두고 있다. 0을 미정의로 보면 오탐이다.
    for el in header.iter("{%s}heading" % NS['hh']):
        t, ref = el.get("type"), el.get("idRef")
        if not ref or ref == "0":
            continue
        if t == "BULLET" and ref not in ids["bullet"]:
            bad.append(f"heading@idRef={ref} (bullet에 없음)")
        if t == "OUTLINE" and ref not in ids["numbering"]:
            bad.append(f"heading@idRef={ref} (numbering에 없음)")
    if bad:
        r.err(2, f"미정의 ID 참조 {len(bad)}건: {bad[:8]}")
    r.info["id_refs_checked"] = True

    # binaryItemIDRef → opf:item → ZIP 실존
    if hpf is not None:
        items = {i.get("id"): i.get("href")
                 for i in hpf.iter("{%s}item" % NS['opf'])}
        names = set(z.namelist())
        for img in section.iter("{%s}img" % NS['hc']):
            ref = img.get("binaryItemIDRef")
            if ref not in items:
                r.err(2, f"binaryItemIDRef={ref}가 content.hpf에 없다")
            elif items[ref] not in names:
                r.err(2, f"{ref} → {items[ref]} 가 ZIP에 없다")

    # itemCnt 대조
    for tag in ("paraProperties", "charProperties", "borderFills", "styles"):
        el = header.find(".//hh:%s" % tag, NS)
        if el is not None and el.get("itemCnt") is not None:
            if int(el.get("itemCnt")) != len(list(el)):
                r.warn(2, f"{tag} itemCnt={el.get('itemCnt')} ≠ 자식 {len(list(el))}")


def _native_front(section, prof):
    """원본에서 그대로 실은 첫머리 문단(overview_fill.yaml) — (문단 집합, 면제 글자모양).

    ★ 2026-09-17. 이 문단들은 **양식 자신의 것**이다. 엔진이 짓는 단순 표의 규칙
      (행 폭 합 = 표 폭, 병합 없는 격자)으로 재면 양식 원본부터 불합격이다 —
      원본 template.hwpx 자체가 L3 오류 30여 건을 낸다(실측).
      글자모양도 「참고」「01」 상자의 흰 글씨(13·20)는 양식 디자인이다.
      단 **초안·안내문 색(draft_color)은 면제하지 않는다** — 남아 있으면 샌 것이다.
    """
    if prof is None:
        return set(), set()
    from . import overview_fill
    spec = overview_fill.load_spec(prof.dir)
    if not spec:
        return set(), set()
    n = int(spec["front_paragraphs"])
    tops = [p for p in section if p.tag == "{%s}p" % NS['hp']][:n]
    with zipfile.ZipFile(prof.template) as z:
        hdr = z.read("Contents/header.xml").decode("utf-8")
        src = z.read("Contents/section0.xml").decode("utf-8")
    colors = spec.get("draft_color") or []
    colors = [colors] if isinstance(colors, str) else colors
    draft = set()
    for c in colors:
        draft |= set(re.findall(rf'<hh:charPr id="(\d+)"[^>]*textColor="{re.escape(c)}"', hdr))
    from .vendor import zip_surgery
    kids = zip_surgery.extract_children(zip_surgery.parse_section(src.encode()).body)[:n]
    native = set(re.findall(r'charPrIDRef="(\d+)"', "".join(kids)))
    return set(tops), native - draft


def _l3(trees, prof, r: Result):
    section = trees.get("Contents/section0.xml")
    if section is None:
        return
    tw = prof.text_width if prof else None
    front, _ = _native_front(section, prof)
    front_tbls = {t for p in front for t in p.iter("{%s}tbl" % NS['hp'])}

    for tb in section.iter("{%s}tbl" % NS['hp']):
        if tb in front_tbls:
            continue
        sz = tb.find("hp:sz", NS)
        want = int(sz.get("width"))
        if tw and want > tw:
            r.err(3, f"표 폭 {want} > 본문폭 {tw}")
        for tr in tb.findall("hp:tr", NS):
            got = sum(int(tc.find("hp:cellSz", NS).get("width"))
                      for tc in tr.findall("hp:tc", NS))
            if got != want:
                r.err(3, f"표 행 폭 합 {got} ≠ 표 폭 {want}")
                break
        nrow, ncol = int(tb.get("rowCnt")), int(tb.get("colCnt"))
        # ★ 병합 칸은 펼쳐서 센다. 전에는 기점 칸만 셌고, 표 안에 든 표의 칸까지
        #   iter() 로 섞어 셌다 — 병합이 있는 표는 전부 「격자 불완전」이었다.
        addrs = set()
        for tc in tb.findall("hp:tr/hp:tc", NS):
            a, sp = tc.find("hp:cellAddr", NS), tc.find("hp:cellSpan", NS)
            r0, c0 = int(a.get("rowAddr")), int(a.get("colAddr"))
            rs = int(sp.get("rowSpan")) if sp is not None else 1
            cs = int(sp.get("colSpan")) if sp is not None else 1
            addrs |= {(r0 + i, c0 + j) for i in range(rs) for j in range(cs)}
        want_grid = {(a, b) for a in range(nrow) for b in range(ncol)}
        if addrs != want_grid:
            r.err(3, f"표 {nrow}x{ncol} cellAddr 격자 불완전 "
                     f"(누락 {sorted(want_grid - addrs)[:4]})")

    maxw = (prof.figure.get("max_width") if prof else None) or tw
    for pic in section.iter("{%s}pic" % NS['hp']):
        o = pic.find("hp:orgSz", NS)
        c = pic.find("hp:curSz", NS)
        sm = pic.find("hp:renderingInfo/hc:scaMatrix", NS)
        if None in (o, c, sm):
            r.err(3, "hp:pic에 orgSz/curSz/scaMatrix가 없다")
            continue
        ow, cw = int(o.get("width")), int(c.get("width"))
        e1 = float(sm.get("e1"))
        if ow and abs(e1 - cw / ow) > 1e-3:
            r.err(3, f"scaMatrix.e1={e1} ≠ curSz/orgSz={cw/ow:.6f}")
        if maxw and cw > maxw:
            r.err(3, f"그림 폭 {cw} > 최대 {maxw}")
        # ★ 그림이 담긴 문단의 들여쓰기까지 더해야 실제 오른쪽 끝이다.
        #   이걸 안 보면 들여쓰기 있는 앵커에서 그림이 조용히 페이지를 벗어난다.
        anc = pic.getparent()
        while anc is not None and anc.tag != "{%s}p" % NS['hp']:
            anc = anc.getparent()
        if anc is not None and tw:
            ls = anc.find("hp:linesegarray/hp:lineseg", NS)
            indent = int(ls.get("horzpos")) if ls is not None else 0
            if cw + indent > tw:
                r.err(3, f"그림 오른쪽 끝 {cw + indent} (폭 {cw} + 들여쓰기 "
                         f"{indent}) > 본문폭 {tw} — 페이지를 벗어난다")
        if pic.find("hp:caption", NS) is None:
            r.warn(3, "hp:pic에 캡션이 없다")

    # 본문 lineseg horzpos+horzsize == text_width
    if tw:
        TC = "{%s}tc" % NS['hp']
        CAP = "{%s}caption" % NS['hp']
        bad = 0
        for p in section.iter("{%s}p" % NS['hp']):
            if p in front:
                continue
            anc = {a.tag for a in p.iterancestors()}
            if TC in anc or CAP in anc:
                continue
            ls = p.find("hp:linesegarray/hp:lineseg", NS)
            if ls is None:
                continue
            if int(ls.get("horzpos")) + int(ls.get("horzsize")) != tw:
                bad += 1
        if bad:
            r.err(3, f"본문 lineseg horzpos+horzsize ≠ {tw} 인 문단 {bad}개")


def _l4(z, trees, prof, r: Result):
    tmpl = prof.template if prof else None
    if tmpl and os.path.exists(tmpl):
        with zipfile.ZipFile(tmpl) as t:
            orig_h = t.read("Contents/header.xml")
        new_h = z.read("Contents/header.xml")
        if orig_h == new_h:
            r.info["header"] = f"원본과 바이트 동일 ({hashlib.sha256(new_h).hexdigest()[:16]})"
        else:
            # ★ 바이트가 달라도 곧바로 위반이 아니다.
            #   참조 규격서(KIMM-DESIGN §2.10)는 "끝번호부터 추가, itemCnt 증가,
            #   기존 ID 불변"을 허용한다. 표준 표 스타일을 못 갖춘 양식에서
            #   borderFill을 덧붙이는 게 그 경우다.
            #   그래서 **바이트 동일성이 아니라 구조적 불변성**으로 판정한다:
            #   기존 id가 속성까지 그대로 있고, 추가분이 전부 뒤 번호인가.
            from . import header_extend
            errs = header_extend.verify_ids_unchanged(orig_h, new_h)
            if errs:
                r.err(4, f"header.xml의 기존 스타일 ID가 변경됐다: {errs[:4]}")
            else:
                added = _added_ids(orig_h, new_h)
                r.info["header"] = (f"기존 ID 불변, {added} 추가됨 "
                                    f"(규격서 §2.10 허용 방식)")
                r.warn(4, f"header.xml에 {added}를 추가했다. "
                          f"기존 ID는 전부 그대로다")

        want_t = prof.template_sha256
        if want_t:
            h = hashlib.sha256()
            with open(tmpl, "rb") as f:
                for ch in iter(lambda: f.read(1 << 20), b""):
                    h.update(ch)
            if h.hexdigest() != want_t:
                r.warn(4, "template.hwpx가 profile 기록 sha256과 다르다 (양식 교체됨?)")

    raw = z.read("Contents/section0.xml").decode("utf-8", errors="replace")
    forb = (prof.writing_rules.get("forbidden_char_prs") if prof else []) or []
    sec_tree = trees.get("Contents/section0.xml")
    _, exempt = _native_front(sec_tree, prof) if sec_tree is not None else (set(), set())
    hit = [c for c in forb if f'charPrIDRef="{c}"' in raw and str(c) not in exempt]
    if hit:
        r.err(4, f"양식 안내문/교정 색상 charPr 사용: {hit}")

    if "<hp:markpenBegin" in raw:
        r.err(4, "형광펜(markpenBegin)이 남아 있다")
    if 'type="MEMO"' in raw:
        r.err(4, "메모(fieldBegin MEMO)가 남아 있다")

    texts = re.findall(r"<hp:t>(.*?)</hp:t>", raw, re.S)
    joined = "".join(texts)

    # ★ 글머리 문자 직접 입력 — **이중 렌더가 실제로 일어나는 문단만** 잡는다.
    #   전에는 문서 전체 텍스트에서 문자만 찾아 무조건 오류로 냈다. 그런데
    #   실측(2026-08-26): 이 양식의 **개요는 paraPr 85(heading=NONE)** 을 쓰고
    #   양식 자신이 `◦ ` 를 문자로 찍는다. 자동 렌더가 없으므로 이중 표시가
    #   아니고, 오히려 문자를 빼면 양식과 달라진다.
    #   → 판정 기준을 「문자 존재」에서 **「BULLET 문단 안의 문자」** 로 좁힌다.
    #   ★ 정규식으로 훑지 않는다. header 에는 자기닫힘 `<hh:paraPr .../>` 가 섞여
    #     있어 `(.*?)</hh:paraPr>` 가 여러 정의를 한 덩어리로 삼킨다. 그러면 id 와
    #     heading 이 서로 다른 문단모양에서 나온다 — 실측으로 BULLET 5개가 1개로 줄었다.
    from lxml import etree as _et
    _hh = "{%s}" % NS["hh"]
    _hp = "{%s}" % NS["hp"]
    bullet_paras = set()
    for pp in _et.fromstring(z.read("Contents/header.xml")).iter(_hh + "paraPr"):
        hd = pp.find(_hh + "heading")
        if hd is not None and (hd.get("type") or "").upper() == "BULLET":
            bullet_paras.add(pp.get("id"))

    for para in _et.fromstring(z.read("Contents/section0.xml")).iter(_hp + "p"):
        if bullet_paras and para.get("paraPrIDRef") not in bullet_paras:
            continue
        body = "".join(t.text or "" for run in para.findall(_hp + "run")
                       for t in run.findall(_hp + "t"))
        for ch, name in (("◦", "◦"), ("", "U+F09F"), ("▪", "▪")):
            if ch in body:
                r.err(4, "BULLET 문단(paraPr "
                         f"{para.get('paraPrIDRef')})의 텍스트에 글머리 문자 "
                         f"{name}가 직접 들어 있다 — 자동 렌더와 이중 표시된다")
                break
    # ── 미해결 표시 ───────────────────────────────────────────────
    # ★ 기계 게이트 사각지대 2호 (형식 위원 적발, 2026-08-26).
    #   전에는 `[FIG-n` / `[TBL-n` **두 가지만** 봤다. 그래서 오케스트레이터가
    #   작성자에게 쓰라고 지시한 `[[미확인: …]]` 마커 30건이 **최종 산출물에
    #   그대로 인쇄됐는데 게이트는 정상을 냈다.**
    #   재무성과표는 값이 한 칸도 없는 채로 통과했다.
    #
    #   교훈은 규칙이 아니라 절차에 있다 — **파이프라인이 새 마커를 도입하면
    #   검증기가 그것을 아는지 같은 커밋에서 확인해야 한다.**
    for pat, label in (
            (r"\[(?:FIG|TBL)-\d+", "그림/표 플레이스홀더"),
            (r"\[\[\s*미확인", "미확인 마커"),
            (r"\[\s*보완\s*필요\s*\]", "보완 필요 표시"),
            (r"(?<![A-Za-z])TBD(?![A-Za-z])", "TBD"),
            (r"\bXX+\b", "자리표시 XX"),
    ):
        hits = re.findall(pat, joined)
        if hits:
            r.err(4, f"미해결 {label} {len(hits)}건이 본문에 남아 있다 "
                     f"(예: {hits[0]!r}) — 최종 산출물에 그대로 인쇄된다")
    r.info["text_chars"] = len(joined)


def _l5(path: str, r: Result, prof, timeout: int = 90):
    """한컴 실렌더. **반드시 별도 프로세스 + 타임아웃**으로 돌린다.

    COM이 대화상자를 띄우면 무한 대기한다(실측). 인프로세스로 부르면 검증
    전체가 멈추므로, 자식 프로세스로 격리하고 시간이 지나면 죽인다.
    """
    import subprocess
    import tempfile

    from .hancom_check import HWP_EXE
    if not os.path.exists(HWP_EXE):
        r.warn(5, "한글이 설치돼 있지 않아 실렌더 검증을 건너뛴다")
        return

    with tempfile.TemporaryDirectory() as td:
        rp = os.path.join(td, "hancom.json")
        cmd = [sys.executable, "-m", "engine.hwpx.hancom_check", path, "--json", rp]
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        try:
            subprocess.run(cmd, cwd=root, timeout=timeout,
                           capture_output=True,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        except subprocess.TimeoutExpired:
            _kill_hwp()
            r.warn(5, f"한컴 COM이 {timeout}초 안에 끝나지 않아 중단했다 "
                      f"(대화상자 대기 의심). 정적 검증 L0~L4는 유효하다")
            return
        if not os.path.exists(rp):
            r.warn(5, "한컴 검증 리포트가 생성되지 않았다")
            return
        with open(rp, encoding="utf-8") as f:
            rep = json.load(f)
    if not rep.get("opened"):
        r.err(5, f"한글에서 열리지 않는다: {rep.get('errors')}")
        return
    r.info["pages"] = rep.get("pages")
    r.info["hancom_text_chars"] = rep.get("text_chars")
    if not rep.get("text_chars"):
        r.err(5, "한글 텍스트 추출이 0자다 — 채점기가 내용을 못 읽는다")
    for e in rep.get("errors", []):
        r.warn(5, e)


def validate(path: str, form_dir: str | None = None, level: int = 5) -> Result:
    r = Result()
    prof = None
    if form_dir:
        try:
            prof = profmod.load(form_dir)
        except Exception as e:                              # noqa: BLE001
            r.warn(0, f"profile 로드 실패: {e}")

    with zipfile.ZipFile(path) as z:
        _l0(z, prof.template if prof else None, r)
        trees = _l1(z, r) if level >= 1 else {}
        if level >= 2:
            _l2(z, trees, r)
        if level >= 3:
            _l3(trees, prof, r)
        if level >= 4:
            _l4(z, trees, prof, r)
    if level >= 5:
        _l5(path, r, prof)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--form")
    ap.add_argument("--level", type=int, default=5, choices=range(0, 6))
    ap.add_argument("--json")
    a = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    r = validate(a.file, a.form, a.level)
    print(f"검증 L0~L{a.level}: 오류 {len(r.errors)} / 경고 {len(r.warnings)}")
    for k, v in r.info.items():
        print(f"  {k}: {v}")
    for w in r.warnings:
        print(f"  [경고] {w}")
    for e in r.errors:
        print(f"  [오류] {e}", file=sys.stderr)
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"errors": r.errors, "warnings": r.warnings,
                       "info": r.info, "exit": r.code}, f,
                      ensure_ascii=False, indent=2)
    return r.code


if __name__ == "__main__":
    sys.exit(main())
