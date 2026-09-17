# -*- coding: utf-8 -*-
"""ZIP 복제 + section0.xml 교체 + BinData/content.hpf 패치.

vendor/zip_surgery.py의 read_zip/write_zip/parse_section/assemble_section을
쓴다. 그게 엔트리 순서·압축타입·XML 선언을 바이트 보존한다.

**header.xml은 절대 건드리지 않는다.** 검증기 L4가 sha256으로 강제한다.
"""
from __future__ import annotations

import os
import re
import sys
import zipfile

_VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

import zip_surgery  # noqa: E402  (vendor)

PNG_MEDIA = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
             "bmp": "image/bmp", "gif": "image/gif"}

SECTION_RE = re.compile(r"^Contents/section(\d+)\.xml$")


def extra_sections(names) -> list[str]:
    """section0 외의 섹션 목록.

    ★ 다중 섹션 양식이 실재한다. 실측: 출연연 연구개발계획서 양식은
    section0~section5 여섯 개다. section0만 교체하면 나머지 다섯 개에
    원본 내용이 그대로 남아 산출물이 15쪽(원본 텍스트 8702자)이 된다.
    우리 본문이 문서 전체를 대체해야 하므로 나머지는 걷어낸다.
    """
    out = []
    for n in names:
        m = SECTION_RE.match(n)
        if m and m.group(1) != "0":
            out.append(n)
    return sorted(out, key=lambda x: int(SECTION_RE.match(x).group(1)))


def drop_sections_from_hpf(hpf_text: str, sections: list[str]) -> str:
    """content.hpf의 manifest item과 spine itemref에서 해당 섹션을 뺀다."""
    for href in sections:
        sid = SECTION_RE.match(href).group(0)
        num = SECTION_RE.match(href).group(1)
        hpf_text = re.sub(
            r'<opf:item\s+id="section%s"[^>]*/>' % num, "", hpf_text)
        hpf_text = re.sub(
            r'<opf:itemref\s+idref="section%s"[^>]*/>' % num, "", hpf_text)
    return hpf_text


def _empty_section(orig: bytes) -> bytes:
    """섹션의 첫 문단(secPr 포함)만 남기고 나머지를 버린다.

    secPr은 첫 문단 첫 run 안에 있어 용지·여백 설정을 담고 있으므로 반드시
    보존해야 한다. 그 뒤 문단들만 걷어내면 빈 섹션이 된다.
    """
    parts = zip_surgery.parse_section(orig)
    children = zip_surgery.extract_children(parts.body)
    if not children:
        return orig
    first = children[0]
    # 첫 문단에서 텍스트만 제거하고 secPr/colPr은 남긴다
    first = re.sub(r"<hp:t>.*?</hp:t>", "<hp:t/>", first, flags=re.S)
    first = re.sub(r"<hp:tbl .*?</hp:tbl>", "", first, flags=re.S)
    first = re.sub(r"<hp:pic .*?</hp:pic>", "", first, flags=re.S)
    return zip_surgery.assemble_section(parts, [first])


def drop_sections_from_rdf(rdf_text: str, sections: list[str]) -> str:
    """container.rdf에서도 해당 섹션 참조를 뺀다.

    ★ content.hpf만 고치면 한글이 파일을 못 연다(실측: Open()이 False).
    container.rdf가 같은 섹션을 rdf:Description 두 벌로 참조하기 때문이다.
    """
    for href in sections:
        # <rdf:Description rdf:about=""><ns0:hasPart ... resource="href"/></rdf:Description>
        rdf_text = re.sub(
            r'<rdf:Description rdf:about="">(?:(?!</rdf:Description>).)*?'
            r'rdf:resource="%s"\s*/>\s*</rdf:Description>' % re.escape(href),
            "", rdf_text, flags=re.S)
        # <rdf:Description rdf:about="href">...</rdf:Description>
        rdf_text = re.sub(
            r'<rdf:Description rdf:about="%s">.*?</rdf:Description>'
            % re.escape(href), "", rdf_text, flags=re.S)
    return rdf_text


def patch_content_hpf(hpf_text: str, images: dict[str, str]) -> str:
    """opf:manifest에 BinData 항목을 추가한다.

    ⚠️ href는 패키지 루트 기준 전체 경로다 (`BinData/image3.png`).
    ⚠️ 정규식 치환으로 처리한다. lxml 재직렬화는 XML 선언의 standalone과
       네임스페이스 접두사 순서를 바꾼다.
    """
    if not images:
        return hpf_text
    add = []
    for bin_id, href in images.items():
        if f'id="{bin_id}"' in hpf_text:
            continue
        ext = href.rsplit(".", 1)[-1].lower()
        media = PNG_MEDIA.get(ext, "image/png")
        add.append(f'<opf:item id="{bin_id}" href="{href}" '
                   f'media-type="{media}" isEmbeded="1"/>')
    if not add:
        return hpf_text
    m = re.search(r"</opf:manifest>", hpf_text)
    if not m:
        raise ValueError("content.hpf에 </opf:manifest>가 없다")
    return hpf_text[:m.start()] + "".join(add) + hpf_text[m.start():]


def build(template: str, output: str, section_xml: bytes,
          images: dict[str, str] | None = None,
          header_xml: bytes | None = None) -> dict:
    """template를 복제하고 section0.xml만 교체. images는 {bin_id: 파일경로}.

    header_xml을 주면 header.xml도 교체한다 (borderFill 덧붙이기 전용).
    **기존 ID를 바꾸는 용도로 쓰면 안 된다** — header_extend.verify_ids_unchanged가
    강제하고 검증기 Q1.5도 구조적으로 확인한다.
    """
    images = images or {}
    entries, order = zip_surgery.read_zip(template)
    modified = {"Contents/section0.xml": section_xml}
    if header_xml is not None:
        modified["Contents/header.xml"] = header_xml

    # 다중 섹션 양식이면 section0 외의 섹션을 **비운다**.
    # ★ ZIP에서 지우면 안 된다. content.hpf와 container.rdf까지 정리해도
    #   한글이 Open()에서 False를 돌려준다(실측). 엔트리는 남기고 내용만 비운다.
    #   대신 빈 섹션마다 빈 페이지가 하나씩 생기므로 호출부에 경고를 돌려준다.
    dropped = extra_sections(order)
    entry_map0 = {e.filename: e for e in entries}
    for name in dropped:
        modified[name] = _empty_section(entry_map0[name].data)

    href_map = {}
    for bin_id, src in images.items():
        ext = os.path.splitext(src)[1].lstrip(".").lower() or "png"
        href = f"BinData/{bin_id}.{ext}"
        href_map[bin_id] = href
        with open(src, "rb") as f:
            data = f.read()
        if href in order:
            modified[href] = data
        else:
            entries.append(zip_surgery.ZipEntry(
                filename=href, data=data,
                compress_type=zipfile.ZIP_STORED))   # PNG는 이미 압축됨
            order.append(href)

    hpf_name = "Contents/content.hpf"
    hpf = next((e for e in entries if e.filename == hpf_name), None)
    if hpf is None:
        raise ValueError("Contents/content.hpf 없음")
    hpf_text = hpf.data.decode("utf-8")
    modified[hpf_name] = patch_content_hpf(hpf_text, href_map).encode("utf-8")



    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    zip_surgery.write_zip(output, entries, order, modified)
    return {"images": href_map, "entries": len(order),
            "emptied_sections": dropped}


def section_parts(template: str):
    """원본 section0.xml의 헤더/루트닫기를 그대로 재사용한다."""
    with zipfile.ZipFile(template) as z:
        return zip_surgery.parse_section(z.read("Contents/section0.xml"))


def assemble(parts, children: list[str]) -> bytes:
    return zip_surgery.assemble_section(parts, children)
