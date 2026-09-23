# -*- coding: utf-8 -*-
"""하네스 조립 파이프라인 실행기 — form_strip → kordoc → 헤더 패치 → 표 폭 재단.

    python $CLAUDE_PLUGIN_ROOT/scripts/harness_assemble.py --run workspace/ai-refrigerant/B_동결3회/c1

`rfp-proposal-harness` 의 `hwpx-writing` SKILL §3-1~§3-3b 를 그대로 옮긴 것이다.
**절차를 바꾸지 않는다** — 3회 실행이 같은 절차를 밟아야 재현성 측정이 성립한다.

## 왜 스크립트로 만들었나

원 SKILL 은 헤더 패치를 **문서 안의 파이썬 블록**으로 준다. 사람이 복사해 붙이는 방식이라
3회 실행에서 한 글자라도 달라지면 그게 곧 비결정성이 된다. 절차 자체를 고정한다.

## 원 SKILL 이 실측으로 경고한 함정 (전부 반영)

| # | 함정 | 안 지키면 |
|---|---|---|
| 3-1 ⓪ | 가이드 주석을 지운 `.build.md` 로 조립 | J-5 FAIL |
| 3-2 | `--h2-marker none` 누락 | 장 제목 번호가 사라진다(조용히) |
| 3-3 ① | 여백 좌우 5669 → **8504** | 서식 미준수 |
| 3-3 ③ | 목록 문단 위 간격 □22/ㅇ14.7pt → **□6/ㅇ0** | 같은 원고가 **10p → 19p** |
| 3-3 ④ | 본문 11.73pt → **11pt**, 표 8.8 → **9pt** | 규정 위반 108회 |
| 3-3b | 여백 패치 후 표 폭 재단 | 본문폭 42,519 에 46,389 표 — 오른쪽 여백 13.6mm 침범 |
| — | `mimetype` 은 **ZIP_STORED** | 파일이 안 열린다 |
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile

def _find_plugin() -> str:
    """설치된 rfp-proposal-harness 를 찾는다.

    ★ 버전을 박아두지 않는다(2026-09-01 정정). 전에는 `0.30.0` 을 하드코딩해
      다른 PC 에 다른 버전이 깔려 있으면 조용히 깨졌다 — 이식성 검증을 하려는
      스크립트 자체가 이식되지 않는 셈이었다.
      여러 버전이 있으면 **가장 높은 것**을 쓴다.
    """
    import glob
    base = os.path.join(os.path.expanduser("~"), ".claude", "plugins", "cache",
                        "jinwoo-skills", "rfp-proposal-harness")
    cands = sorted(glob.glob(os.path.join(base, "*")),
                   key=lambda p: [int(x) if x.isdigit() else 0
                                  for x in os.path.basename(p).split(".")])
    if not cands:
        raise SystemExit(
            "rfp-proposal-harness 가 설치돼 있지 않다.\n"
            "  /plugin marketplace add JINWOOYOO86/claude-skills-marketplace\n"
            "  /plugin install rfp-proposal-harness@jinwoo-skills")
    return cands[-1]


# ★ 2026-09-07 플러그인 탐색을 호출 시점으로 미룬다.
#   전에는 모듈 최상단에서 찾아 **import 만 해도 SystemExit** 이 났다.
#   그 탓에 플러그인이 없는 PC 에서 pytest 가 2건 실패했다(실측).
#   조립과 무관한 freeze_zip_times 를 쓰려는 테스트까지 죽었고,
#   「설치 전에 먼저 테스트로 확인하라」는 안내가 거짓이 된다.
def plugin_paths():
    """(scripts 디렉터리, 기본 명세 경로) — 조립할 때만 불린다."""
    plugin = _find_plugin()
    return (os.path.join(plugin, "skills", "hwpx-writing", "scripts"),
            os.path.join(plugin, "skills", "template-extraction", "assets",
                         "default-form", "default_form_spec.json"))

def resolve_page_budget(run_dir: str, asked: int | None) -> tuple[int, str]:
    """이 회차의 쪽수를 **한 곳에서** 정한다 → (쪽수, 출처 설명).

    ★ 2026-09-15. 전에는 분량이 세 군데에 흩어져 서로를 몰랐다 —
      ⓐ 이 스크립트의 `--max-pages`(조립 하드캡),
      ⓑ 워크스페이스 `50_form_spec.json` 의 `page_budget.hard_max`(gate_pages 가 읽는다),
      ⓒ 같은 파일의 `page_budget.total` · `chapters`(장별 배분 판정).
      `demo-15p` 는 ⓐ 로만 15쪽이 됐고 ⓑ 는 15, ⓒ 는 **10 인 채로 남아** 있었다.
      gate_pages 는 `total > pb["total"]` 이면 장별 허용오차를 0.5p → 0.25p 로 조인다.
      즉 15쪽 판은 **늘 가장 엄한 모드**로 돌고 있었다(코드상 사실).

    규칙(사용자, 2026-09-09): 말하지 않으면 10쪽, 말하면 그 분량.
    말한 값은 **목표이자 상한**이다 — 둘을 갈라 두면 위의 조임이 다시 살아난다.
    """
    import json
    spec_path = os.path.join(run_dir, "50_form_spec.json")
    spec = None
    if os.path.exists(spec_path):
        spec = json.load(open(spec_path, encoding="utf-8"))

    if asked is None:
        if spec and "hard_max" in spec.get("page_budget", {}):
            n = int(spec["page_budget"]["hard_max"])
            return n, f"{os.path.basename(spec_path)} page_budget.hard_max"
        return 10, "기본값(분량 미지정)"

    if spec is None:
        return asked, "--max-pages (워크스페이스 명세 없음)"

    pb = spec.setdefault("page_budget", {})
    if pb.get("total") == asked and pb.get("hard_max") == asked:
        return asked, "--max-pages (명세와 일치)"

    old_total = pb.get("total") or asked
    ch = pb.get("chapters") or {}
    if ch and old_total:
        r = asked / old_total
        scaled = {k: round(v * r, 1) for k, v in ch.items()}
        gap = round(asked - sum(scaled.values()), 1)
        if gap:                                   # 배분 합이 총량과 어긋나지 않게 한다
            big = max(scaled, key=lambda k: scaled[k])
            scaled[big] = round(scaled[big] + gap, 1)
        pb["chapters"] = scaled
    pb["total"] = asked
    pb["hard_max"] = asked
    pb["note_max_pages"] = (f"--max-pages {asked} 로 조립하면서 맞췄다. "
                            "분량은 한 곳에서만 정한다 — 조립 하드캡과 gate_pages 가 "
                            "서로 다른 수를 보면 통과가 통과가 아니다.")
    json.dump(spec, open(spec_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return asked, f"--max-pages → {os.path.basename(spec_path)} 에 반영"


MARGIN = ('<hp:margin header="4252" footer="4252" gutter="0" '
          'left="8504" right="8504" top="5668" bottom="4252"/>')
FONTS = ["함초롬바탕", "함초롬돋움", "한양신명조", "한양중고딕", "HY견고딕"]


def run(cmd, **kw):
    """하위 프로세스를 돌린다.

    ★ 출력을 **UTF-8 로 읽는다** (2026-09-15 실측). `text=True` 만 주면 파이썬은
      로케일 인코딩으로 읽는데, 한국어 윈도에서는 그게 cp949 다. 자식들은
      (PYTHONIOENCODING=utf-8 인 파이썬도, Node 인 kordoc 도) UTF-8 로 쓰므로
      조립 로그가 통째로 깨져 나왔다 — 「PASS ��� �옍議� 0嫄�」.
      기능은 멀쩡한데 **고장난 것처럼 보이는** 종류라, 남의 PC 에서 먼저 의심받는다.
    """
    kw.setdefault("encoding", "utf-8")
    r = subprocess.run(cmd, capture_output=True, text=True,
                       errors="replace", **kw)
    return r


def patch_header(raw: str, out: str) -> None:
    """SKILL §3-3 을 그대로 옮긴 헤더 패치."""
    zin = zipfile.ZipFile(raw)
    sec0 = zin.read("Contents/section0.xml").decode("utf-8")

    def ptxt(p):
        return "".join(re.findall(r"<hp:t>([^<]*)</hp:t>", p)).strip()

    h2, h3, body = set(), set(), set()
    for para in re.findall(r"<hp:p\b.*?</hp:p>", sec0, re.S):
        cr = re.search(r'charPrIDRef="(\d+)"', para)
        if not cr:
            continue
        t = ptxt(para)
        tgt = (h2 if re.match(r"^\d+\.\s", t)
               else h3 if re.match(r"^\d+-\d+\.\s", t) else body)
        tgt.add(cr.group(1))
    h2 -= body
    h3 -= body

    zout = zipfile.ZipFile(out, "w")
    for it in zin.infolist():
        d = zin.read(it.filename)
        if it.filename.startswith("Contents/section"):
            s = d.decode("utf-8")
            s = re.sub(r"<hp:margin[^>]*/>", MARGIN, s)
            d = s.encode("utf-8")
        if it.filename.endswith("header.xml"):
            h = d.decode("utf-8")
            for f in FONTS:
                h = h.replace('face="%s"' % f, 'face="돋움"')
            for pid, prev, left in [("8", "600", "0"), ("9", "0", "1100"),
                                    ("10", "0", "2200")]:
                def fix(m, prev=prev, left=left):
                    s = m.group(0)
                    s = re.sub(r'<hc:prev value="\d+"',
                               '<hc:prev value="%s"' % prev, s)
                    s = re.sub(r'<hc:left value="\d+"',
                               '<hc:left value="%s"' % left, s)
                    s = re.sub(r'<hc:intent value="-?\d+"',
                               '<hc:intent value="-1650"', s)
                    return s
                h = re.sub(r'<hh:paraPr id="%s".*?</hh:paraPr>' % pid, fix,
                           h, flags=re.S)

            def norm(m):
                cid, blk = m.group(1), m.group(0)
                if cid in h2 or cid in h3:
                    return blk

                def sz(mm):
                    v = int(mm.group(1))
                    if 1000 <= v <= 1250:
                        v = 1100
                    elif 850 <= v <= 999:
                        v = 900
                    return 'height="%d"' % v
                return re.sub(r'height="(\d+)"', sz, blk)
            h = re.sub(r'<hh:charPr id="(\d+)".*?</hh:charPr>', norm, h,
                       flags=re.S)

            def h3fix(m):
                blk = m.group(0)
                if m.group(1) not in h3:
                    return blk
                # ★ 2026-09-07 절 제목 13pt → **11pt**(사용자 지시).
                #   「1.」 같은 장만 16pt, 하위 절은 전부 본문과 같은 11pt 로 고정한다.
                #   굵기는 유지한다 — 크기가 같아지면 굵기가 유일한 제목 신호다.
                blk = re.sub(r'height="\d+"', 'height="1100"', blk)
                return (blk if "<hh:bold" in blk
                        else blk.replace("</hh:charPr>", "<hh:bold/></hh:charPr>"))
            h = re.sub(r'<hh:charPr id="(\d+)".*?</hh:charPr>', h3fix, h,
                       flags=re.S)
            d = h.encode("utf-8")
        zi = zipfile.ZipInfo(it.filename, date_time=it.date_time)
        zi.compress_type = (zipfile.ZIP_STORED if it.filename == "mimetype"
                            else zipfile.ZIP_DEFLATED)
        zout.writestr(zi, d)
    zout.close()
    zin.close()


SEC_RE = re.compile(r"^\s*\d+(-\d+)?\.\s")
# 장 제목만(1. 2. 3.) — 절(1-1.)은 제외한다.
CHAP_RE = re.compile(r"^\s*\d+\.\s")

# 조립에 쓰는 kordoc 을 정확한 버전으로 고정한다. 이유는 [2/4] 단계 주석 참조.
KORDOC = "kordoc@4.12.3"


def insert_section_gaps(path: str) -> int:
    """절 제목 문단 앞에 빈 문단을 하나씩 넣는다.

    ★ 사용자 제출 요건: **절이 바뀔 때마다 빈 줄.**

    실측(2026-08-27): 하네스 조립 경로로 만든 3판이 절 제목 17개 중
    **16 / 16 / 15 곳에서 빈 줄이 없었다.** 앞 절 마지막 줄과 다음 절 제목이
    바짝 붙어 절 경계가 눈으로 구분되지 않는다.

    작성자에게 맡기면 매번 갈리므로 **조립 단계에서 넣는다.**
    (이 저장소의 `engine/hwpx/build_hwpx.py` 가 이미 같은 처리를 한다 — 그쪽은 0곳이다.)

    문서 첫 절 앞에는 넣지 않는다. 표 안 문단은 건드리지 않는다.
    """
    from lxml import etree
    HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
        infos = {i.filename: i for i in z.infolist()}

    root = etree.fromstring(data["Contents/section0.xml"])

    # ★ 빈 문단이 쓸 **본문 글자 모양**을 먼저 정한다.
    #   실측 결함(2026-09-01): 제목 문단을 복제해 빈 문단을 만들었더니
    #   charPr 이 제목 것(13pt 굵게 · 16pt)으로 남아 gate_form 이 잡았다 —
    #   F-9 규격 외 33건 · F-10 굵기 18%(상한 5%).
    #   빈 줄은 눈에 안 보이므로 사람은 못 잡는다. 게이트가 잡았다.
    #
    #   본문 charPr 은 하드코딩하지 않는다(양식마다 다르다) —
    #   **표 밖 텍스트 문단에서 가장 많이 쓰인 charPr** 을 본문으로 본다.
    from collections import Counter
    cnt = Counter()
    for p in root.iter(HP + "p"):
        if any(a.tag.endswith("}tbl") for a in p.iterancestors()):
            continue
        if not "".join(t.text or "" for t in p.iter(HP + "t")).strip():
            continue
        for run in p.iter(HP + "run"):
            if run.find(HP + "t") is not None:
                cnt[run.get("charPrIDRef")] += 1
                break
    body_char = cnt.most_common(1)[0][0] if cnt else None

    added = 0
    first = True
    for para in list(root.iter(HP + "p")):
        # 표 안 문단은 제외
        if any(a.tag.endswith("}tbl") for a in para.iterancestors()):
            continue
        txt = "".join(t.text or "" for t in para.iter(HP + "t")).strip()
        if not SEC_RE.match(txt) or len(txt) > 60:
            continue
        if first:                     # 문서 첫 절 앞에는 넣지 않는다
            first = False
            continue
        prev = para.getprevious()
        if prev is not None:
            ptxt = "".join(t.text or "" for t in prev.iter(HP + "t")).strip()
            if ptxt == "":
                continue              # 이미 빈 줄이 있다
            # ★ 2026-09-10 사용자 지시: 대제목(1. 2. 3.) 바로 다음에는 넣지 않는다.
            #   「1. 연구 배경」 다음에 바로 「1-1. …」이 오는 경우,
            #   그 사이에 빈 줄을 넣으면 제목만 둥둥 떠 있는 모양이 된다.
            #   절 사이의 여백은 필요하지만 장→절 경계는 아니다.
            if CHAP_RE.match(ptxt) and len(ptxt) <= 60:
                continue
        blank = etree.fromstring(etree.tostring(para))
        for run in blank.findall(HP + "run"):
            for t in run.findall(HP + "t"):
                run.remove(t)
            if body_char:             # ★ 제목 서식을 물려받지 않게 본문으로 되돌린다
                run.set("charPrIDRef", body_char)
        for ls in blank.findall(HP + "linesegarray"):
            blank.remove(ls)          # 줄 수가 달라지므로 한글이 재계산하게 둔다
        para.addprevious(blank)
        added += 1

    data["Contents/section0.xml"] = etree.tostring(
        root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(path, "w") as o:
        for n in names:
            o.writestr(infos[n], data[n],
                       zipfile.ZIP_STORED if n == "mimetype" else zipfile.ZIP_DEFLATED)
    return added


def insert_object_gaps(path: str) -> int:
    """그림·표 **앞뒤에 빈 문단**을 넣는다.

    ★ 사용자 요건(2026-09-14): 그림과 표는 앞뒤로 한 줄씩 떨어져야 한다.

    실측: 원고(.build.md)에는 앞뒤 빈 줄이 다 있는데 **kordoc 이 먹는다.**
      그림 3장 앞 0 · 뒤 0, 표 6개 앞 0 · 뒤 2.
      마크다운을 고쳐도 안 되므로 조립 단계에서 넣는다.

    본문 charPr 을 물려주는 이유는 `insert_section_gaps` 와 같다 —
    캡션 문단을 복제하면 굵기·크기가 따라와 게이트가 잡는다.
    """
    from collections import Counter

    from lxml import etree
    HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
        infos = {i.filename: i for i in z.infolist()}

    root = etree.fromstring(data["Contents/section0.xml"])

    cnt = Counter()
    for para in root.iter(HP + "p"):
        if any(a.tag.endswith("}tbl") for a in para.iterancestors()):
            continue
        if not "".join(t.text or "" for t in para.iter(HP + "t")).strip():
            continue
        for run in para.iter(HP + "run"):
            if run.find(HP + "t") is not None:
                cnt[run.get("charPrIDRef")] += 1
                break
    body_char = cnt.most_common(1)[0][0] if cnt else None

    def is_blank(p):
        if p is None:
            return True                    # 문서 경계는 빈 줄로 친다
        if p.find("." + "//" + HP + "pic") is not None:
            return False
        if p.find("." + "//" + HP + "tbl") is not None:
            return False
        return not "".join(t.text or "" for t in p.iter(HP + "t")).strip()

    def make_blank(model):
        b = etree.fromstring(etree.tostring(model))
        for obj in list(b.iter(HP + "pic")) + list(b.iter(HP + "tbl")):
            obj.getparent().remove(obj)
        for run in b.findall(HP + "run"):
            for t in run.findall(HP + "t"):
                run.remove(t)
            if body_char:
                run.set("charPrIDRef", body_char)
        for ls in b.findall(HP + "linesegarray"):
            b.remove(ls)
        return b

    # ★ 양식 첫머리(제목 상자·표지·개요표)에는 빈 줄을 넣지 않는다 (2026-09-22 실측).
    #   문서 맨 앞에 붙어 있는 표 문단들이 양식 첫머리다. 그 뒤에 빈 줄이 한 줄
    #   들어가자 요약표가 1쪽에 못 들어가 **1쪽이 제목만 남고 통째로 버려졌다**
    #   (10쪽 중 1쪽이 빈 쪽 — 쪽수 게이트는 「10쪽」이라 통과시켰다).
    #   첫머리 뒤에는 어차피 제목 문단이 와서 제 여백을 갖는다.
    tops = [x for x in root if x.tag == HP + "p"]
    front = set()
    for e in tops:
        if e.find("." + "//" + HP + "tbl") is None:
            break
        front.add(id(e))

    added = 0
    for para in list(root.iter(HP + "p")):
        if any(a.tag.endswith("}tbl") for a in para.iterancestors()):
            continue
        has_obj = (para.find("." + "//" + HP + "pic") is not None
                   or para.find("." + "//" + HP + "tbl") is not None)
        if not has_obj:
            continue
        if id(para) in front:
            continue
        if not is_blank(para.getprevious()):
            para.addprevious(make_blank(para))
            added += 1
        if not is_blank(para.getnext()):
            para.addnext(make_blank(para))
            added += 1

    data["Contents/section0.xml"] = etree.tostring(
        root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(path, "w") as o:
        for n in names:
            o.writestr(infos[n], data[n],
                       zipfile.ZIP_STORED if n == "mimetype"
                       else zipfile.ZIP_DEFLATED)
    return added


def normalize_font_size(path: str, pt: float) -> tuple[int, dict]:
    """문서의 **모든** 글자를 한 크기로 맞춘다 — 제목도 표도 (2026-09-23 사용자 지시).

    「모든 글자의 폰트를 11pt 로 하도록 규칙을 전면 수정해」.

    양식 원본은 장 제목 16pt · 절 제목 11pt · 표 9pt · 표지 16.13pt 로 갈린다.
    요강이 「돋움 11pt」 하나만 적었으므로 그 값으로 전부 모은다.

    ★ 표는 좁아진 칸에 글자가 안 들어갈 수 있다. 실측(구조 축 채점):
      간트표 월 칸 폭 10.1mm 인데 11pt 돋움 두 자 + 셀 여백은 11.4mm 다.
      한글은 칸을 넘치면 **줄을 바꾸거나 칸을 늘린다** — 표가 높아지고 쪽수가 는다.
      그래서 이 함수는 **쪽수 검사보다 먼저** 돌고, 넘치면 조립이 멈춘다.

    원칙 1 을 지킨다 — 기존 글자모양은 두고 **크기만 바꾼 복제본을 뒤 번호로**
    덧붙여 run 이 그쪽을 가리키게 한다.
    """
    import re as _re

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
        infos = {i.filename: i for i in z.infolist()}

    hdr = data["Contents/header.xml"].decode("utf-8")
    sec = data["Contents/section0.xml"].decode("utf-8")
    want = int(round(pt * 100))

    items, size = {}, {}
    for m in _re.finditer(r'(?s)<hh:charPr id="(\d+)".*?</hh:charPr>', hdr):
        items[m.group(1)] = m.group(0)
        h = _re.search(r'height="(\d+)"', m.group(0))
        if h:
            size[m.group(1)] = int(h.group(1))

    used = set(_re.findall(r'charPrIDRef="(\d+)"', sec))
    before = {}
    for i in used:
        if i in size:
            k = f"{size[i] / 100:g}pt"
            before[k] = before.get(k, 0) + 1

    need = [i for i in used if i in size and size[i] != want]
    if not need:
        return 0, before

    nxt = max(map(int, items)) + 1
    mapping, clones = {}, []
    for oid in sorted(need, key=int):
        clone = _re.sub(r'^<hh:charPr id="\d+"', f'<hh:charPr id="{nxt}"',
                        items[oid])
        clone = _re.sub(r'height="\d+"', f'height="{want}"', clone)
        clones.append(clone)
        mapping[oid] = str(nxt)
        nxt += 1

    hdr = hdr.replace("</hh:charProperties>",
                      "".join(clones) + "</hh:charProperties>", 1)
    cm = _re.search(r'<hh:charProperties itemCnt="(\d+)"', hdr)
    if cm:
        hdr = hdr.replace(cm.group(0),
                          f'<hh:charProperties itemCnt="{int(cm.group(1)) + len(clones)}"', 1)

    moved = 0

    def _swap(m):
        nonlocal moved
        old = m.group(1)
        if old in mapping:
            moved += 1
            return f'charPrIDRef="{mapping[old]}"'
        return m.group(0)

    sec = _re.sub(r'charPrIDRef="(\d+)"', _swap, sec)

    data["Contents/header.xml"] = hdr.encode("utf-8")
    data["Contents/section0.xml"] = sec.encode("utf-8")
    with zipfile.ZipFile(path, "w") as o:
        for n in names:
            o.writestr(infos[n], data[n],
                       zipfile.ZIP_STORED if n == "mimetype"
                       else zipfile.ZIP_DEFLATED)
    return moved, before


def normalize_line_spacing(path: str, pct: int,
                           include_tables: bool = False) -> tuple[int, dict]:
    """줄간격을 통일한다. **표 안은 기본으로 제외한다**(2026-09-23 사용자 결정).

    본문(표 밖)은 규정값으로 맞추고, 표 안은 **원래 값을 유지하되 하나로 모은다.**
    표가 160% 가 되면 성기게 보인다는 판단이라, 규정값 적용은 본문까지만 한다.

    다만 표 안에 **섞인 값**은 남기지 않는다 — 심사가 「70% 줄간격도 일부
    포함되어」라고 집어낸 것이 그 잡값 2문단이었다. 표 안은 가장 많이 쓰인
    값 하나로 모은다. 규정을 표까지 걸고 싶으면 명세에
    `style.line_spacing_include_tables: true` 를 적는다.

    ★ 실측 결함(2026-09-22, 심사 81점). 대회 요강이 「줄간격 160%」를 정했는데
      산출물은 이랬다.

          160%  196문단 (48.8%)   ← 표 밖 본문. 조립 도구가 맞춰 준다
          130%  204문단 (50.7%)   ← **전부 표 안**. 양식 원본 값이 남았다
           70%    2문단           ← 역시 표 안

      심사평: 「문단의 약 절반에 130% 줄간격이 적용되고 70%도 일부 포함되어
      160% 서식이 문서 전반에 일관되게 유지되지 않았습니다」 — 양식 일관성 9/15.
      **한 자도 틀리지 않았다.**

      우리 게이트는 표 밖 본문만 재고 통과시켰다. 사람 눈에도 안 보인다
      (표 안이 좁은 것은 자연스러워 보인다). **문서 전체를 세야 보인다.**

    원칙 1 을 지킨다 — 기존 문단모양은 건드리지 않고 **줄간격만 바꾼 복제본을
    뒤 번호로 덧붙여** 문단이 그쪽을 가리키게 한다.
    """
    import re as _re

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
        infos = {i.filename: i for i in z.infolist()}

    hdr = data["Contents/header.xml"].decode("utf-8")
    sec = data["Contents/section0.xml"].decode("utf-8")

    cur = {}
    for m in _re.finditer(r'<hh:paraPr id="(\d+)"(.*?)</hh:paraPr>', hdr, _re.S):
        ls = _re.search(r'<hh:lineSpacing[^>]*type="([^"]*)"[^>]*value="(-?\d+)"',
                        m.group(2))
        if ls:
            cur[m.group(1)] = (ls.group(1), int(ls.group(2)))

    spans = [(m.start(), m.end())
             for m in _re.finditer(r"<hp:tbl\b.*?</hp:tbl>", sec, _re.S)]

    def _in_tbl(pos):
        return any(a <= pos < b for a, b in spans)

    body, tbl, before = set(), set(), {}
    for m in _re.finditer(r'<hp:p\b[^>]*paraPrIDRef="(\d+)"', sec):
        i = m.group(1)
        (tbl if _in_tbl(m.start()) else body).add(i)
        if i in cur:
            k = f"{cur[i][0]} {cur[i][1]}"
            before[k] = before.get(k, 0) + 1

    # PERCENT 가 아닌 것(고정값 등)은 건드리지 않는다 — 양식이 일부러 정한 값일
    # 수 있고, 복제기가 PERCENT 만 다룬다.
    def pc(i):
        return i in cur and cur[i][0] == "PERCENT"

    need = {i: pct for i in body if pc(i) and cur[i][1] != pct}
    if include_tables:
        need.update({i: pct for i in tbl if pc(i) and cur[i][1] != pct})
    elif tbl:
        w = {}
        for m in _re.finditer(r'<hp:p\b[^>]*paraPrIDRef="(\d+)"', sec):
            i = m.group(1)
            if _in_tbl(m.start()) and pc(i):
                w[cur[i][1]] = w.get(cur[i][1], 0) + 1
        if w:
            main = max(w, key=lambda k: w[k])
            need.update({i: main for i in tbl if pc(i) and cur[i][1] != main})

    if not need:
        return 0, before

    # 복제본을 **뒤 번호로** 덧붙인다 (원칙 1 — 기존 항목은 손대지 않는다).
    #   engine 을 부르지 않는다: 이 파일은 플러그인으로도 나가 단독 실행된다.
    items = dict(_re.findall(r'(?s)<hh:paraPr id="(\d+)".*?</hh:paraPr>', hdr)
                 ) if False else {}
    for m in _re.finditer(r'(?s)<hh:paraPr id="(\d+)".*?</hh:paraPr>', hdr):
        items[m.group(1)] = m.group(0)
    nxt = max(map(int, items)) + 1
    mapping, clones = {}, []
    for oid in need:
        xml = items[oid]
        clone = _re.sub(r'^<hh:paraPr id="\d+"', f'<hh:paraPr id="{nxt}"', xml)
        clone, n = _re.subn(r'(<hh:lineSpacing type="PERCENT" value=")\d+(")',
                            rf"\g<1>{int(need[oid])}\g<2>", clone)
        if not n:
            continue
        clones.append(clone)
        mapping[oid] = str(nxt)
        nxt += 1
    if not mapping:
        return 0, before
    hdr = hdr.replace("</hh:paraProperties>", "".join(clones) + "</hh:paraProperties>", 1)
    cntm = _re.search(r'<hh:paraProperties itemCnt="(\d+)"', hdr)
    if cntm:
        hdr = hdr.replace(cntm.group(0),
                          f'<hh:paraProperties itemCnt="{int(cntm.group(1)) + len(clones)}"', 1)
    new_hdr = hdr.encode("utf-8")
    moved = 0

    def _swap(m):
        nonlocal moved
        old = m.group(1)
        if old in mapping:
            moved += 1
            return m.group(0).replace(f'paraPrIDRef="{old}"',
                                      f'paraPrIDRef="{mapping[old]}"')
        return m.group(0)

    sec = _re.sub(r'<hp:p\b[^>]*paraPrIDRef="(\d+)"', _swap, sec)

    data["Contents/header.xml"] = new_hdr
    data["Contents/section0.xml"] = sec.encode("utf-8")
    with zipfile.ZipFile(path, "w") as o:
        for n in names:
            o.writestr(infos[n], data[n],
                       zipfile.ZIP_STORED if n == "mimetype"
                       else zipfile.ZIP_DEFLATED)
    return moved, before


def keep_heading_with_body(path: str) -> int:
    """장·절 제목이 쪽 끝에 홀로 남지 않게 한다 (2026-09-23 심사 지적).

    실측: 3쪽이 「2. 연구 목표」와 「2-1. 최종 목표」 두 제목만 남고 152pt 가 비었다.
    제목 문단의 `breakSetting/@keepWithNext` 가 0 이라 본문이 다음 쪽으로 넘어가도
    제목은 앞 쪽에 남는다. **고아 제목**이라 부르고, 구조 점수에서 깎인다.

    캡션에 쓴 수법과 같다 — 기존 문단모양을 두고 `keepWithNext="1"` 복제본을
    뒤 번호로 덧붙여 제목 문단이 그쪽을 가리키게 한다(원칙 1).

    제목 판별은 글자 크기로 한다 — 본문보다 큰 charPr 을 쓰거나 굵은 문단이
    제목이다. 양식마다 스타일 id 가 다르므로 번호를 박지 않는다.
    """
    import re as _re

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
        infos = {i.filename: i for i in z.infolist()}

    hdr = data["Contents/header.xml"].decode("utf-8")
    sec = data["Contents/section0.xml"].decode("utf-8")

    size = {}
    for m in _re.finditer(r'<hh:charPr id="(\d+)"(.*?)</hh:charPr>', hdr, _re.S):
        h = _re.search(r'height="(\d+)"', m.group(2))
        if h:
            size[m.group(1)] = int(h.group(1)) / 100

    # 표 밖 문단만 본다. 「N.」 또는 「N-N.」 로 시작하는 문단이 장·절 제목이다.
    spans = [(m.start(), m.end())
             for m in _re.finditer(r"<hp:tbl\b.*?</hp:tbl>", sec, _re.S)]
    heads = set()
    for m in _re.finditer(r'(?s)<hp:p\b[^>]*paraPrIDRef="(\d+)".*?</hp:p>', sec):
        if any(a <= m.start() < b for a, b in spans):
            continue
        txt = "".join(_re.findall(r"<hp:t>(.*?)</hp:t>", m.group(0), _re.S))
        txt = _re.sub(r"<[^>]+>", "", txt).strip()
        # ★ **절 제목(N-N.)만** 묶는다 (2026-09-23 실측).
        #   장 제목(N.)까지 묶었더니 장이 통째로 다음 쪽으로 밀려 앞 쪽에
        #   208pt 가 비었고 문서가 11쪽이 됐다. 장 제목이 쪽머리에 오는 것은
        #   어색하지 않다 — 어색한 것은 **절 제목만 남고 본문이 넘어가는** 경우다.
        if _re.match(r"^\d+-\d+\.\s+\S", txt) and len(txt) <= 60:
            heads.add(m.group(1))
    if not heads:
        return 0

    items = {}
    for m in _re.finditer(r'(?s)<hh:paraPr id="(\d+)".*?</hh:paraPr>', hdr):
        items[m.group(1)] = m.group(0)
    nxt = max(map(int, items)) + 1
    mapping, clones = {}, []
    for oid in sorted(heads, key=int):
        xml = items.get(oid)
        if xml is None or 'keepWithNext="0"' not in xml:
            continue
        clone = _re.sub(r'^<hh:paraPr id="\d+"', f'<hh:paraPr id="{nxt}"', xml)
        clone = clone.replace('keepWithNext="0"', 'keepWithNext="1"', 1)
        clones.append(clone)
        mapping[oid] = str(nxt)
        nxt += 1
    if not mapping:
        return 0

    hdr = hdr.replace("</hh:paraProperties>",
                      "".join(clones) + "</hh:paraProperties>", 1)
    cm = _re.search(r'<hh:paraProperties itemCnt="(\d+)"', hdr)
    if cm:
        hdr = hdr.replace(cm.group(0),
                          f'<hh:paraProperties itemCnt="{int(cm.group(1)) + len(clones)}"', 1)

    moved = 0

    def _swap(m):
        nonlocal moved
        old = m.group(1)
        if old in mapping and not any(a <= m.start() < b for a, b in spans):
            moved += 1
            return m.group(0).replace(f'paraPrIDRef="{old}"',
                                      f'paraPrIDRef="{mapping[old]}"')
        return m.group(0)

    sec = _re.sub(r'<hp:p\b[^>]*paraPrIDRef="(\d+)"', _swap, sec)

    data["Contents/header.xml"] = hdr.encode("utf-8")
    data["Contents/section0.xml"] = sec.encode("utf-8")
    with zipfile.ZipFile(path, "w") as o:
        for n in names:
            o.writestr(infos[n], data[n],
                       zipfile.ZIP_STORED if n == "mimetype"
                       else zipfile.ZIP_DEFLATED)
    return moved


def keep_caption_with_table(path: str) -> int:
    """표 캡션(과 그 뒤 빈 줄)을 **다음 문단과 함께** 두어 표에서 갈리지 않게 한다.

    ★ 2026-09-22 실렌더로 잡았다. 쪽마다 아래 여백이 없어 표는 이미 셀 단위로 나뉘고
      있었는데, **캡션만 앞 쪽에 남고 표가 다음 쪽에서 시작**했다
      (4쪽 끝 「[표 1] 개발내용 축별 최종 목표」 · 5쪽 첫 줄이 그 표의 머리글).
      사용자에게는 이것이 「표가 넘어간다」로 보인다.

    한글의 「다음 문단과 함께」(paraPr/breakSetting/@keepWithNext)를 캡션에 건다.
    캡션과 표 사이에는 `insert_object_gaps` 가 넣은 빈 줄이 있으므로 그 빈 줄에도 건다.
    기존 문단모양은 건드리지 않고 **keepWithNext 만 다른 복제본을 뒤 번호로 덧붙인다.**
    """
    import re as _re
    from lxml import etree
    HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

    with zipfile.ZipFile(path) as z:
        data = {n: z.read(n) for n in z.namelist()}
        infos = {i.filename: i for i in z.infolist()}
    hdr = data["Contents/header.xml"].decode("utf-8")
    root = etree.fromstring(data["Contents/section0.xml"])

    tops = [p for p in root if p.tag == HP + "p"]
    targets = []
    for i, p in enumerate(tops):
        if p.find(f".//{HP}tbl") is None:
            continue
        j = i - 1
        while j >= 0:                      # 표 앞의 빈 줄과 캡션을 함께 잡는다
            txt = "".join(tops[j].itertext()).strip()
            if txt == "" or txt.startswith("[표"):
                targets.append(tops[j])
                if txt.startswith("[표"):
                    break
                j -= 1
            else:
                break
    if not targets:
        return 0

    ids = [int(x) for x in _re.findall(r'<hh:paraPr id="(\d+)"', hdr)]
    nxt = max(ids) + 1
    clones, mapping = [], {}
    for p in targets:
        src = p.get("paraPrIDRef")
        if src in mapping:
            continue
        m = _re.search(rf'<hh:paraPr id="{src}".*?</hh:paraPr>', hdr, _re.S)
        if not m:
            continue
        xml = _re.sub(r'^<hh:paraPr id="\d+"', f'<hh:paraPr id="{nxt}"', m.group(0))
        xml, k = _re.subn(r'(<hh:breakSetting[^>]*?)keepWithNext="0"', lambda mm: mm.group(1) + 'keepWithNext="1"', xml)
        if not k:
            continue
        clones.append(xml)
        mapping[src] = str(nxt)
        nxt += 1
    if not clones:
        return 0
    m = _re.search(r'<hh:paraProperties\s+itemCnt="(\d+)"\s*>', hdr)
    close = hdr.find("</hh:paraProperties>", m.end())
    hdr = (hdr[:m.start()] + f'<hh:paraProperties itemCnt="{int(m.group(1)) + len(clones)}">'
           + hdr[m.end():close] + "".join(clones) + hdr[close:])
    n = 0
    for p in targets:
        if p.get("paraPrIDRef") in mapping:
            p.set("paraPrIDRef", mapping[p.get("paraPrIDRef")])
            n += 1

    data["Contents/header.xml"] = hdr.encode("utf-8")
    data["Contents/section0.xml"] = etree.tostring(root, encoding="UTF-8",
                                                   xml_declaration=True, standalone=True)
    with zipfile.ZipFile(path, "w") as zo:
        for name in data:
            it = infos[name]
            zi = zipfile.ZipInfo(name, date_time=it.date_time)
            zi.compress_type = it.compress_type
            zi.external_attr = it.external_attr
            zo.writestr(zi, data[name])
    return n


def unset_table_treat_as_char(path: str, value: str = "0") -> int:
    """표의 「글자처럼 취급」을 **value 로 맞춘다** (hp:pos/@treatAsChar).

    ★ 2026-09-10 사용자 지시로 기본값은 **해제(0)** 다. kordoc 산출물도 양식 원본도
      `1` 이었다. 표를 독립 개체로 두면 앞뒤 여백이 예측 가능하다.

    ★★ **2026-09-23 정정 — 2026-09-22 에 적은 설명은 틀렸다.**
      그때 「해제하면 표가 쪽 경계에서 나뉘지 못해 통째로 밀린다」고 적고
      `0` 10쪽 · `1` 11쪽을 그 근거로 들었다. **인과를 거꾸로 읽었다** —
      0 쪽이 짧았던 것은 표가 못 나뉘어서가 아니라 **잘 나뉘어 자리를 채웠기
      때문**이다. 그 오독 때문에 「쪽 경계에서 나누려면 1 이어야 한다」는
      반대 결론을 명세에 박아 넣었다.

      같은 원고로 다시 쟀다(11pt·줄간격 160% 통일 상태).

          treatAsChar=1   12쪽 · 쪽 하단 총 공백 1,233pt · 표가 통째로 밀림
          treatAsChar=0   10쪽 · 쪽 하단 총 공백   355pt · 본문 감김 0곳

      **해제가 두 쪽 짧고 공백이 3분의 1 이하다.** `pageBreak="CELL"` 과
      `repeatHeader="1"` 은 해제 상태에서도 그대로 작동한다.
      기본값은 **해제(0)** 이고, 켜야 할 이유가 생기면 그때 명세로 켠다.

    양식 명세 `style.table_treat_as_char: true` 로 켠다. 적지 않으면 예전대로 해제한다.
    그림은 건드리지 않는다 — 지시가 표에 한정됐다.
    """
    from lxml import etree
    HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
        infos = {i.filename: i for i in z.infolist()}

    root = etree.fromstring(data["Contents/section0.xml"])
    n = 0
    for tbl in root.iter(HP + "tbl"):
        pos = tbl.find(HP + "pos")
        if pos is not None and pos.get("treatAsChar") != value:
            pos.set("treatAsChar", value)
            n += 1

    data["Contents/section0.xml"] = etree.tostring(
        root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(path, "w") as o:
        for name in names:
            o.writestr(infos[name], data[name],
                       zipfile.ZIP_STORED if name == "mimetype"
                       else zipfile.ZIP_DEFLATED)
    return n


def freeze_zip_times(path: str, stamp=(1980, 1, 1, 0, 0, 0)) -> None:
    """ZIP 타임스탬프를 상수로 고정한다.

    ★ 실측(2026-09-07): 같은 원고를 세 번 조립하니 sha256 이 **세 번 다 달랐다.**
      엔트리 내용은 9개 전부 바이트 동일했고 **date_time 만** 달랐다.
      절대원칙 4(같은 입력이 같은 바이트)는 컨테이너까지 고정해야 성립한다.
      재현자료로 「같은 명령이 같은 파일을 만든다」를 보이려면 이 한 단계가 필요하다.
    """
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
        comp = {i.filename: i.compress_type for i in z.infolist()}
    with zipfile.ZipFile(path, "w") as o:
        for n in names:
            zi = zipfile.ZipInfo(n, date_time=stamp)
            zi.compress_type = comp[n]
            zi.external_attr = 0o600 << 16
            o.writestr(zi, data[n])


def page_count(path: str, cap: int) -> int | None:
    """한컴으로 쪽수를 재고 하드캡과 대조한다.

    ★ 제출 요건이 **10쪽을 넘으면 안 된다**이므로 추정으로 넘기지 않는다.
      pywin32 가 RPC 로 죽는 PC 가 있어 PowerShell 경로를 쓴다.
    """
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine.hwpx import hancom_check
    r = hancom_check.check_via_powershell(path)
    return r.get("pages")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="회차 디렉터리 (30_proposal.md 가 있는 곳)")
    # ★ 기본값 10 은 사용자 규칙이다(2026-09-09).
    #   「분량을 말하지 않으면 10쪽, 말하면 그 분량에 맞춘다.」
    #   임의로 늘리지 마라 — 분량은 제출 요건이지 권고가 아니다.
    ap.add_argument("--max-pages", type=int, default=None,
                    help="쪽수. 이 값이 목표이자 상한이다. 생략하면 워크스페이스 "
                         "50_form_spec.json 의 page_budget.hard_max, 그것도 없으면 10")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    SCRIPTS, SPEC = plugin_paths()      # 여기서 처음 필요해진다
    d = os.path.abspath(a.run)
    src = os.path.join(d, "30_proposal.md")
    build = os.path.join(d, "30_proposal.build.md")
    raw = os.path.join(d, "30_raw.hwpx")
    final = os.path.join(d, "30_proposal.hwpx")
    if not os.path.exists(src):
        print("원고가 없다: " + src)
        return 2

    max_pages, why = resolve_page_budget(d, a.max_pages)
    print(f"[분량] {max_pages}쪽 — {why}")

    print("[1/4] form_strip")
    r = run([sys.executable, os.path.join(SCRIPTS, "form_strip.py"),
             "--in", src, "--out", build, "--spec", SPEC],
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    print("   " + (r.stdout or r.stderr).strip().splitlines()[-1])
    if not os.path.exists(build):
        return 2

    # ★ 그림은 사용자가 요청할 때만 (2026-09-17). 요청 목록은 requirements.md 의
    #   `figures:` 한 줄이고, 선언이 없으면 요청이 없는 것으로 본다.
    #   다른 PC 실행에서 요청 안 한 그림 두 장이 들어갔다 — 규칙은 문서에만 있었다.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import check_figures
    ok, msg = check_figures.check(build, os.path.join(d, "requirements.md"))
    print("[그림] 요청한 것만 들어갔는가")
    for line in msg.splitlines():
        print("   " + line.strip())
    if not ok:
        return 2

    print("[2/4] kordoc generate")
    # ★ 버전을 고정한다 (2026-09-07). 전에는 `kordoc@^4` 였는데 부동 범위라
    #   npx 가 그때그때 최신 4.x 를 받았다. **4.13.0 이 골격 마커를 회귀시킨다** —
    #   같은 원고(build.md 바이트 동일)로:
    #       4.12.3 → □34 · ○64   (커밋된 산출물과 일치)
    #       4.13.1 → □12 · ○34   + 절 제목에 □ 를 본문 텍스트로 주입
    #   □ 가 제목 앞에 붙으면 SEC_RE(`^\d+(-\d+)?\. `)가 하나도 안 맞아
    #   절 앞 빈 줄 삽입이 **0건으로 조용히 무동작**했다(요구사항 미충족).
    #   절대원칙 4(같은 입력이 같은 바이트)는 도구 버전까지 고정해야 성립한다.
    figdir = os.path.join(d, "figures")
    imgopt = ["--image-dir", figdir] if os.path.isdir(figdir) else []
    if imgopt:
        print(f"   그림 디렉터리: {figdir}")
    r = run(["npx", "-y", KORDOC, "generate", build, "-o", raw, *imgopt,
             "--preset", "계획서", "--font", "gothic", "--pt", "11",
             "--line-spacing", "160", "--paper", "A4",
             "--h2-marker", "none", "--bullet2", "○",
             "--fonts", "body=돋움,heading=돋움,table=돋움"],
            cwd=d, shell=True)
    tail = [l for l in (r.stdout or "").splitlines() if l.strip()][-3:]
    for l in tail:
        print("   " + l)
    if not os.path.exists(raw):
        print("   kordoc 실패: " + (r.stderr or "")[:300])
        return 2

    print("[3/4] 헤더 패치 (여백·글꼴·글자크기·목록 간격)")
    patch_header(raw, final)
    print("   → " + os.path.basename(final))

    print("[4/4] 표 폭 재단")
    r = run([sys.executable, os.path.join(SCRIPTS, "fix_table_width.py"),
             "--hwpx", final],
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    out = (r.stdout or r.stderr).strip().splitlines()
    print("   " + (out[-1] if out else "(출력 없음)"))

    print("[5/6] 절 제목 앞 빈 줄 삽입")
    added = insert_section_gaps(final)
    print(f"   빈 문단 {added}개 삽입")

    og = insert_object_gaps(final)
    print(f"   그림·표 앞뒤 빈 줄 {og}개 삽입")
    # 표 「글자처럼 취급」 — 기본은 해제. 해제가 쪽수·공백 모두 유리하다(2026-09-23 실측)
    import json as _json
    spec_path = os.path.join(d, "50_form_spec.json")
    want_char = "0"
    if os.path.exists(spec_path):
        with open(spec_path, encoding="utf-8") as f:
            want_char = "1" if (_json.load(f).get("style") or {}).get(
                "table_treat_as_char") else "0"
    khb = keep_heading_with_body(final)
    print(f"   제목을 본문에 붙임(고아 제목 방지) {khb}개")
    kwn = keep_caption_with_table(final)
    print(f"   캡션을 표에 붙임(다음 문단과 함께) {kwn}개")
    # ★ 글자 크기를 문서 전체에 맞춘다 — 제목도 표도 (2026-09-23 사용자 지시)
    with open(spec_path, encoding="utf-8") as f:
        _st = _json.load(f).get("style") or {}
    if _st.get("uniform_font_pt"):
        _pt = float(_st["uniform_font_pt"])
        fmoved, fbefore = normalize_font_size(final, _pt)
        fmix = " · ".join(f"{k} {v}run" for k, v in sorted(fbefore.items()))
        print(f"   글자 크기 {_pt:g}pt 로 통일 — {fmoved}run 옮김  (전: {fmix})")

    # ★ 줄간격을 문서 전체에 맞춘다 — 표 안까지 (2026-09-22 심사 결함)
    with open(spec_path, encoding="utf-8") as f:
        _ls = (_json.load(f).get("style") or {}).get("line_spacing")
    if _ls:
        with open(spec_path, encoding="utf-8") as f:
            _inc = bool((_json.load(f).get("style") or {}
                         ).get("line_spacing_include_tables"))
        moved, before = normalize_line_spacing(final, int(_ls), _inc)
        mix = " · ".join(f"{k} {v}문단" for k, v in sorted(before.items()))
        print(f"   줄간격 본문 {_ls}%"
              + ("  · 표 안도 함께" if _inc else "  · 표 안은 한 값으로 통일")
              + f" — {moved}문단 옮김  (전: {mix})")

    tac = unset_table_treat_as_char(final, want_char)
    print(f"   표 글자처럼취급 {'적용' if want_char == '1' else '해제'} {tac}개"
          + ("  (쪽 경계에서 셀 단위로 나뉜다)" if want_char == "1"
             else "  (표가 쪽 경계를 넘나들며 자리를 채운다)"))

    freeze_zip_times(final)          # 재현성: 컨테이너 시각 고정

    # ★ 심사 배점 검사 — 81점을 맞고 넣었다 (2026-09-23).
    #   줄간격·논리 충돌·실행 조건·중복·과압축. 배점 손실이 큰 순서다.
    print("[6/7] 심사 배점 검사 (rubric)")
    import check_rubric
    rub_fail, rub_warn = check_rubric.check(build, final, spec_path)
    if rub_fail:
        print("   ✖ 심사 배점 항목 위반 — 작성자에게 되돌린다")
        return 2
    print(f"   ✔ 실패 0건 · 경고 {len(rub_warn)}건")

    print(f"[7/7] 쪽수 하드캡 검사 (상한 {max_pages}쪽)")
    pages = page_count(final, max_pages)
    if pages is None:
        print("   ⚠ 한컴을 실행하지 못해 **미측정**. 제출 전 반드시 수동 확인할 것")
        return 1
    if pages > max_pages:
        print(f"   ✖ {pages}쪽 — 상한 {max_pages}쪽 초과. 산문을 줄여야 한다")
        return 2
    print(f"   ✔ {pages}쪽 (상한 {max_pages})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
