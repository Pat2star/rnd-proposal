# -*- coding: utf-8 -*-
"""Markdown + form profile + 그림 → HWPX.

    PYTHONPATH=$CLAUDE_PLUGIN_ROOT python -m engine.hwpx.build_hwpx --form forms/strategic-2027 \\
        --md workspace/demo/proposal_draft.md \\
        --figures workspace/demo/figures \\
        --out workspace/demo/build/proposal_final.hwpx \\
        --dump-section workspace/demo/build/section0.xml

플레이스홀더 결합 계약 (계획 Part C):
    rp-figure가 figures/figure_manifest.json에 placeholder_title을 원문 그대로
    기록해 두고, 여기서 MD의 설명과 대조한다. 유사도가 낮으면 exit 2.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys

from . import borderfill, figure as figmod, header_index, mdblocks, package, profile, render
from .mdblocks import Block

JOSA = re.compile(r"(의|과|와|및|을|를|이|가|은|는|에|로|으로)$")


def normalize_title(t: str) -> str:
    t = re.sub(r"[\s()\[\]{}·,.\-_/]+", "", (t or "").lower())
    return JOSA.sub("", t)


def title_similarity(a: str, b: str) -> float:
    na, nb = normalize_title(a), normalize_title(b)
    if na == nb:
        return 1.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def load_manifest(fig_dir: str) -> dict:
    p = os.path.join(fig_dir, "figure_manifest.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return {it["placeholder"]: it for it in data.get("items", [])}


def resolve_placeholder(block: Block, manifest: dict, warnings: list,
                        errors: list) -> dict | None:
    """★ 제목 대조 — 사용자 요청의 핵심."""
    item = manifest.get(block.placeholder)
    if not item:
        errors.append(f"{block.placeholder}: manifest에 항목이 없다 "
                      f"(MD 설명: '{block.title}') → rp-figure로 반환")
        return None
    rec = item.get("placeholder_title", "")
    sim = title_similarity(block.title, rec)
    if sim >= 0.999:
        pass
    elif sim >= 0.85:
        warnings.append(f"{block.placeholder}: 정규화 후 일치 "
                        f"(MD '{block.title}' / 그림 '{rec}')")
    elif sim >= 0.6:
        warnings.append(f"⚠ {block.placeholder}: 제목이 다르다 — "
                        f"MD '{block.title}' / 그림 '{rec}' (유사도 {sim:.2f}). "
                        f"사람이 확인할 것")
    else:
        errors.append(f"{block.placeholder}: 제목 불일치 — MD '{block.title}' / "
                      f"그림 '{rec}' (유사도 {sim:.2f}) → rp-figure로 반환")
        return None
    return item


def _standard_table_specs() -> list[dict]:
    """표준 표 스타일이 요구하는 borderFill 조합 (stub 없는 표 기준)."""
    from .consts import zone_spec
    seen, out = set(), []
    for r in range(4):
        for c in range(4):
            s = zone_spec(r, c, 4)
            key = (s["l"], s["r"], s["t"], s["b"], s["fill"])
            if key not in seen:
                seen.add(key)
                out.append(s)
    return out


# 줄간격 규정이 적용되는 「본문」 역할. 제목·표·캡션·개요는 양식 서식을 그대로 쓴다.
BODY_ROLES = ("body", "bullet_level_0", "bullet_level_1",
              "bullet_level_2", "bullet_level_3")


def build(form_dir: str, md_path: str, out_path: str,
          fig_dir: str | None = None, dump_section: str | None = None,
          tables_dir: str | None = None, extend_header: bool = False) -> dict:
    prof = profile.load(form_dir)
    hidx = header_index.from_hwpx(prof.template)

    # 표준 표 스타일을 양식이 못 갖췄으면 header.xml 끝에 덧붙인다(기존 ID 불변).
    new_header = None
    header_added = []
    if extend_header:
        from . import header_extend
        adds = header_extend.plan_additions(hidx, _standard_table_specs())
        if adds:
            with __import__("zipfile").ZipFile(prof.template) as z:
                orig = z.read("Contents/header.xml")
            new_header, mapping = header_extend.extend(orig, adds)
            errs = header_extend.verify_ids_unchanged(orig, new_header)
            if errs:
                raise RuntimeError(f"header 확장이 기존 ID를 건드렸다: {errs}")
            header_added = list(mapping.values())
            hidx = header_index.build(new_header)

    # ── 본문 줄간격 — 공고문·작성요령이 정했을 때만 ─────────────────────
    # ★ 2026-09-17 사용자 규칙: 「공고문·작성요령에 본문 줄간격 규정이 있으면 따르고,
    #   없으면 양식을 유지한다.」 실측: 번들 양식 7종의 원문에 **본문** 줄간격 규정은
    #   0건이다(NST 계열 개요 구간 130% 만 있고, 그건 개요 전용 서식이 이미 따른다).
    #   그래서 이 분기는 profile 에 `writing_rules.line_spacing.body` 가 **근거와 함께**
    #   적혔을 때만 돈다. 근거 없는 값은 받지 않는다 — 가독성 취향으로 양식을 바꾸지 않는다.
    #
    #   기존 문단모양은 건드리지 않는다(절대원칙 1). 줄간격만 다른 **복제본을 뒤 번호로
    #   덧붙이고** 본문 역할이 그걸 가리키게 한다. 검사는 「추가분을 걷어내면 원본과
    #   바이트 동일」로 이 방식을 허용한다.
    rule = (prof.writing_rules.get("line_spacing") or {})
    body_pct = rule.get("body")
    spacing_note = None
    if body_pct:
        if not str(rule.get("source") or "").strip():
            raise RuntimeError("writing_rules.line_spacing.body 에 근거(source)가 없다 — "
                               "공고문·작성요령의 문구를 인용하라. 규정이 없으면 양식을 유지한다")
        from . import header_extend
        body_roles = [r for r in BODY_ROLES if prof.role(r).get("para")]
        targets = {}
        for r in body_roles:
            pid = str(prof.role(r)["para"])
            if int(prof.role(r).get("line_spacing_pct") or 0) != int(body_pct):
                targets[pid] = int(body_pct)
        if targets:
            if new_header is None:
                with __import__("zipfile").ZipFile(prof.template) as z:
                    new_header = z.read("Contents/header.xml")
            new_header, pmap = header_extend.clone_parapr_spacing(new_header, targets)
            hidx = header_index.build(new_header)
            for r in body_roles:
                role = prof.roles.get(r) or prof.role(r)
                pid = str(role.get("para"))
                if pid in pmap:
                    role["para"] = pmap[pid]
                    role["line_spacing_pct"] = int(body_pct)
            spacing_note = (f"본문 줄간격 {body_pct}% 적용 — 근거: {rule['source']} "
                            f"(문단모양 {sorted(pmap.items())} 복제 추가)")

    with open(md_path, encoding="utf-8") as f:
        md = f.read()

    blocks = mdblocks.parse(md)
    manifest = load_manifest(fig_dir) if fig_dir else {}
    warnings: list[str] = []
    errors: list[str] = []

    ctx = render.RenderCtx(profile=prof, ids=render.IdGen(prof),
                           warnings=warnings, text_width=prof.text_width)
    resolver = borderfill.BorderFillResolver(
        hidx, stub_cols=int(prof.table.get("stub_cols") or 0),
        table_border_fill=prof.table.get("tbl_border_fill"))

    # 본문 인라인 [FIG-1] → "그림 1" 치환용 번호표
    order = [b.placeholder for b in blocks if b.kind in ("figure", "table_ref")]
    numbers = {}
    fig_n = tbl_n = 0
    for ph in order:
        if ph.startswith("FIG"):
            fig_n += 1
            numbers[ph] = fig_n
        else:
            tbl_n += 1
            numbers[ph] = tbl_n

    def sub_inline(t: str) -> str:
        def rep(m):
            ph = f"{m.group(1)}-{m.group(2)}"
            if ph in numbers:
                return f"{'그림' if ph.startswith('FIG') else '표'} {numbers[ph]}"
            warnings.append(f"본문의 {ph} 참조를 해소하지 못했다")
            return m.group(0)
        return mdblocks.FIG_INLINE.sub(rep, t)

    children: list[str] = []
    images: dict[str, str] = {}
    used_manifest: list[str] = []
    prologue = prof.prologue_run() or ""
    first = True
    fig_count = 0

    # ── 양식 첫머리를 원본 그대로 (2026-09-17) ─────────────────────────
    # overview_fill.yaml 이 있는 양식은 표지 상자·개요표를 **원본 표 그대로** 싣고
    # 값 칸만 채운다. 원고의 「개요」 구간은 표로 옮겼으니 본문에서 뺀다.
    # 원본 첫 문단이 구역 설정(secPr)을 이미 품고 있으므로 prologue 는 다시 붙이지 않는다.
    from . import overview_fill
    ofs = overview_fill.resolve_spec(form_dir, prof.template)
    if ofs:
        head = ofs.get("section_heading")

        def is_overview_heading(b):
            t = b.text.strip()
            if head:
                return t.startswith(head)
            m = overview_fill.NUM_HEADING.match(t)
            return not m or m.group(1) == "0"        # 번호 없는 제목 · 「0. 요약문」

        sect, rest, inside, seen_body = [], [], False, False
        doc_title = None
        for b in blocks:
            if b.kind == "heading" and b.level == 1 and not seen_body:
                if is_overview_heading(b):
                    if doc_title is None and not b.text.strip().startswith(("개요", "0")):
                        doc_title = b.text.strip()
                    inside = True
                    continue
                inside, seen_body = False, True
            elif b.kind == "heading" and b.level == 1 and head:
                inside = b.text.strip().startswith(head)
                if inside:
                    continue
            (sect if inside else rest).append(b)
        values, budget, owarn, leftover, nmatch = overview_fill.collect(sect, ofs)
        if doc_title and doc_title != head:
            values.setdefault("__제목__", [doc_title])
        auto = ofs.get("source") == "auto"
        if auto and nmatch < overview_fill.MIN_MATCH_AUTO:
            # 원고가 양식 개요와 맞지 않는다 — 엉뚱한 칸에 넣느니 예전 방식으로 짓는다
            warnings.append(f"양식 첫머리를 자동으로 채우지 못했다(원고 개요와 맞은 항목 {nmatch}개 "
                            f"< {overview_fill.MIN_MATCH_AUTO}) — 원고 표를 새로 지었다")
        else:
            front, fwarn = overview_fill.front_paragraphs(prof.template, ofs, values, budget)
            warnings.extend(owarn + fwarn)
            if not values:
                errors.append("원고에 개요 구간이 없거나 비어 있다 — 개요표를 채울 값이 없다")
            children.extend(front)
            # 양식에 자리가 없는 표·글은 개요표 바로 뒤에 원고 그대로 싣는다(버리지 않는다)
            blocks = leftover + rest
            prologue = ""
            first = False
            if front and not any("secPr" in x for x in front):
                # 첫 문단(구역 설정)을 싣지 않았다면 첫 표 문단 앞에 prologue 를 붙여야 한다
                errors.append("양식 첫 문단(구역 설정)이 첫머리에 없다 — 명세의 front_keep 을 확인하라")

    # ── 개요 구간 전용 서식 ────────────────────────────────────────────
    # ★ 실측(2026-08-26): 이 양식은 개요에 **자기만의 서식 규칙**을 명시한다.
    #   원본 section0 para 167 — `※ 2page 분량 제한 준수(글자 10point, 줄간격 130%)`
    #   그리고 원본 개요 글머리 문단 전부가 다음 조합이다:
    #       paraPr 85 (heading=NONE, lineSpacing PERCENT 130) + charPr 156 (10pt)
    #   heading=NONE 이므로 **자동 글머리가 없고**, 양식이 `◦ ` 와 ` - ` 를
    #   **문자로 직접** 찍는다. 본문(paraPr 24/25, BULLET, 180%)과 정반대다.
    #
    #   즉 절대원칙 2(글머리 문자 직접 입력 금지)는 **본문 규칙**이고,
    #   개요는 양식 자신이 예외로 규정한 구간이다. 양식을 따른다.
    #
    #   P-패널 형식 위원이 C-2 로 적발(−7.0): 우리 산출물이 개요에 12/11pt·180%
    #   본문 서식을 그대로 써서 명시 규격을 위반하고 있었다.
    ov0 = prof.role("overview_bullet_level_0")
    ov_active = bool(ov0)
    in_overview = False

    def overview_role(block) -> tuple[str | None, str]:
        """개요 구간이면 (역할명, 앞에 붙일 글머리 문자)를 준다."""
        if not (ov_active and in_overview and block.kind == "bullet"):
            return None, ""
        lvl = min(block.level, 1)
        role = f"overview_bullet_level_{lvl}"
        if not prof.role(role):
            return None, ""
        return role, str(prof.role(role).get("bullet_char") or "")

    for b in blocks:
        # 개요 구간 판정 — `# 개요` 부터 다음 1수준 제목 직전까지
        if b.kind == "heading" and b.level == 1:
            in_overview = b.text.strip().startswith("개요")

        if b.kind == "figure":
            item = resolve_placeholder(b, manifest, warnings, errors)
            if not item:
                continue
            src = item["file"]
            if not os.path.isabs(src):
                src = os.path.join(os.path.dirname(os.path.abspath(md_path)), src)
                if not os.path.exists(src) and fig_dir:
                    src = os.path.join(fig_dir, os.path.basename(item["file"]))
            if not os.path.exists(src):
                errors.append(f"{b.placeholder}: 그림 파일 없음 {src}")
                continue
            fig_count += 1
            bin_id = f"image{fig_count + 100}"
            images[bin_id] = src
            # ★ 그림 앵커 문단에 들여쓰기가 있으면 그만큼 폭을 줄여야 한다.
            #   실측: 2번 양식의 figure_anchor는 paraPr 4(들여쓰기 3000)라
            #   본문폭을 그대로 쓰면 그림이 오른쪽으로 3000만큼 넘친다.
            anchor_indent = int(prof.role("figure_anchor").get("indent_left") or 0)
            avail = min(int(prof.figure.get("max_width") or prof.text_width),
                        prof.text_width - anchor_indent)
            if anchor_indent:
                warnings.append(
                    f"{b.placeholder}: 그림 앵커 들여쓰기 {anchor_indent} 때문에 "
                    f"최대 폭을 {avail}로 줄였다")
            geo = figmod.geometry(
                src, avail,
                respect_dpi=bool(prof.figure.get("respect_png_dpi")),
                width_pct=float(item.get("width_pct", 1.0)))
            used_manifest.append(b.placeholder)
            children.append(render.empty_paragraph(ctx))
            children.append(render.paragraph(
                ctx, "figure_anchor",
                inner=render.picture(ctx, geo, bin_id,
                                     item.get("caption", b.title),
                                     numbers[b.placeholder], os.path.basename(src)),
                vertsize=geo["curSz"][1], horzpos=0,
                prologue=(prologue if first else "")))
            first = False
            children.append(render.empty_paragraph(ctx))
            continue

        if b.kind == "table_ref":
            item = resolve_placeholder(b, manifest, warnings, errors)
            path = None
            if item:
                path = item.get("file")
                used_manifest.append(b.placeholder)
            elif tables_dir:
                cand = os.path.join(
                    tables_dir, f"tbl{int(b.placeholder.split('-')[1]):02d}.md")
                path = cand if os.path.exists(cand) else None
            if not path or not os.path.exists(path):
                errors.append(f"{b.placeholder}: 표 파일을 찾지 못했다 ({b.title})")
                continue
            with open(path, encoding="utf-8") as f:
                sub = mdblocks.parse(f.read())
            tb = next((x for x in sub if x.kind == "table"), None)
            if not tb:
                errors.append(f"{b.placeholder}: {path} 에 MD 표가 없다")
                continue
            b = tb  # 아래 table 처리로 흘려보낸다

        if b.kind == "table":
            xml, meta = render.table(ctx, b.rows, resolver)
            children.append(render.paragraph(
                ctx, "table_anchor", inner=xml, vertsize=meta["height"],
                horzpos=0, prologue=(prologue if first else "")))
            first = False
            continue

        role = render.role_for(b, prof)
        ov_role, ov_char = overview_role(b)
        if ov_role:
            role = ov_role
        # ★ 새 제목 앞에는 빈 문단을 하나 넣는다 (사용자 지시, 2026-08-19).
        #   실렌더에서 "연계 수요명" 같은 제목이 앞 표에 바짝 붙어 절이 어디서
        #   갈리는지 눈으로 구분되지 않았다. 양식이 제목 문단모양에 위쪽 여백을
        #   주지 않기 때문이다(paraPr 35/36/37 전부 margin 0).
        #   문서 첫 블록 앞에는 넣지 않는다.
        if b.kind == "heading" and not first:
            children.append(render.empty_paragraph(ctx))
        children.append(render.paragraph(
            ctx, role, ov_char + sub_inline(b.text),
            prologue=(prologue if first else "")))
        first = False

    # manifest에 있는데 본문에 안 쓰인 항목
    for ph, item in manifest.items():
        if ph not in used_manifest:
            errors.append(f"{ph}: manifest에 있으나 본문에 등장하지 않는다 "
                          f"('{item.get('placeholder_title')}')")

    if not children:
        children.append(render.paragraph(ctx, "body", "", prologue=prologue))

    parts = package.section_parts(prof.template)
    section = package.assemble(parts, children)

    if dump_section:
        os.makedirs(os.path.dirname(os.path.abspath(dump_section)), exist_ok=True)
        with open(dump_section, "wb") as f:
            f.write(section)

    info = package.build(prof.template, out_path, section, images, new_header)
    if info.get("emptied_sections"):
        n = len(info["emptied_sections"])
        warnings.append(
            f"다중 섹션 양식이라 section1~{n}을 비웠다. ZIP에서 지우면 한글이 "
            f"파일을 열지 못하므로 엔트리는 남긴다(실측). "
            f"결과 문서 끝에 빈 페이지가 {n}장 붙는다. "
            f"★★ 그 섹션이 **별첨 서식**이면 비우면 안 된다. "
            f"실측(2026-08-26): strategic-2027-dist 의 section1 은 "
            f"「참고3 출연연 연구기획 기반 제안서 요약본 양식(안)」 96KB 짜리 "
            f"**필수 첨부**였다. 비운 채 제출하면 서식 누락이다. "
            f"양식마다 section1+ 이 무엇인지 확인하고, 별첨이면 원본을 그대로 두거나 "
            f"내용을 채워야 한다")
    if spacing_note:
        # 경고로 올린다 — 양식 서식에서 벗어났다는 사실은 사람이 봐야 한다.
        warnings.append(spacing_note)
    if header_added:
        warnings.append(
            f"표준 표 스타일을 위해 borderFill {header_added}를 header.xml 끝에 "
            f"추가했다 (기존 ID 불변 확인 완료)")
    return {"out": out_path, "blocks": len(blocks), "paragraphs": len(children),
            "figures": fig_count, "images": info["images"],
            "warnings": warnings, "errors": errors, "numbers": numbers,
            "header_added": header_added}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--form", required=True)
    ap.add_argument("--md", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--figures")
    ap.add_argument("--tables")
    ap.add_argument("--dump-section")
    ap.add_argument("--requirements",
                    help="요청한 그림 목록(figures:)이 든 requirements.md. "
                         "생략하면 원고 위쪽에서 찾는다")
    ap.add_argument("--extend-header", action="store_true",
                    help="표준 표 스타일에 필요한 borderFill을 header.xml 끝에 추가"
                         " (기존 ID는 불변)")
    a = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # ★ 그림은 사용자가 요청할 때만 (2026-09-17). 다른 PC 실행에서 이 경로로
    #   요청 안 한 그림 두 장이 들어갔다. 빌드하기 전에 막는다.
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.join(root, "scripts"))
    import check_figures
    ok, msg = check_figures.check(
        a.md, a.requirements or check_figures.find_requirements(a.md))
    if not ok:
        print("[그림] 요청한 것만 들어갔는가")
        print(msg)
        return 2

    r = build(a.form, a.md, a.out, a.figures, a.dump_section, a.tables,
              extend_header=a.extend_header)
    print(f"빌드 완료 → {r['out']}")
    print(f"  블록 {r['blocks']} → 문단 {r['paragraphs']}, 그림 {r['figures']}")
    for w in r["warnings"]:
        print(f"  [경고] {w}")
    for e in r["errors"]:
        print(f"  [오류] {e}", file=sys.stderr)
    return 2 if r["errors"] else (1 if r["warnings"] else 0)


if __name__ == "__main__":
    sys.exit(main())
