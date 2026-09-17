# -*- coding: utf-8 -*-
"""Markdown → 블록 IR.

플레이스홀더 계약 (docs/quality_rubric.md Q2, 계획 Part C):
  `[FIG-1: 연구 개요도]`  독립된 한 줄  → figure 블록
  `[TBL-1: 선행연구 비교]` 독립된 한 줄  → table 블록 (tables/*.md 로드)
  `[FIG-1]`               문장 안        → "그림 1" 텍스트로 치환 (조립 시)

글머리 규칙:
  `- `      → level 0        `  - ` (2칸) → level 1        `    - ` (4칸) → level 2
  ★ 본문 텍스트에 ◦ - ▪ 를 직접 넣지 않는다. paraPr의 heading이 자동 렌더한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

FIG_LINE = re.compile(r"^\s*\[(FIG|TBL)-(\d+)\s*:\s*(.+?)\s*\]\s*$")
FIG_INLINE = re.compile(r"\[(FIG|TBL)-(\d+)\]")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
NUMBERED = re.compile(r"^(\s*)\d+[.)]\s+(.*)$")
BOLD = re.compile(r"\*\*(.+?)\*\*")
ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
CODE = re.compile(r"`([^`]+)`")


@dataclass
class Block:
    kind: str                  # heading | bullet | body | table | figure | table_ref
    text: str = ""
    level: int = 0             # heading 1~6, bullet 0~3
    rows: list = field(default_factory=list)      # table: [[cell,...], ...]
    has_header: bool = True
    placeholder: str = ""      # "FIG-1"
    title: str = ""            # 플레이스홀더의 설명 원문 — 제목 대조의 기준선
    source_line: int = 0


def strip_inline(text: str, keep_bold: bool = False) -> str:
    """인라인 마크업 제거.

    양식에 본문용 bold charPr이 없으면 **굵게**를 살릴 수 없다(header.xml을
    고쳐야 하는데 ID 불변 원칙과 충돌). 그래서 기본은 마크업만 벗긴다.
    """
    text = CODE.sub(r"\1", text)
    text = BOLD.sub(r"\1", text)
    text = ITALIC.sub(r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)   # [링크](url) → 링크
    return text.strip()


def _bullet_level(indent: str) -> int:
    """공백 2칸 = 1수준. 탭은 4칸으로 환산."""
    n = len(indent.replace("\t", "    "))
    return min(n // 2, 3)


def parse(md: str) -> list[Block]:
    lines = md.replace("\r\n", "\n").split("\n")
    blocks: list[Block] = []
    i = 0
    para_buf: list[str] = []

    def flush():
        nonlocal para_buf
        if para_buf:
            t = strip_inline(" ".join(para_buf))
            if t:
                blocks.append(Block("body", t, source_line=i))
            para_buf = []

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()

        if not line.strip():
            flush()
            i += 1
            continue

        m = FIG_LINE.match(line)
        if m:
            flush()
            kind = "figure" if m.group(1) == "FIG" else "table_ref"
            blocks.append(Block(kind, placeholder=f"{m.group(1)}-{m.group(2)}",
                                title=m.group(3), source_line=i + 1))
            i += 1
            continue

        m = HEADING.match(line)
        if m:
            flush()
            blocks.append(Block("heading", strip_inline(m.group(2)),
                                level=len(m.group(1)), source_line=i + 1))
            i += 1
            continue

        # MD 표: | a | b | 다음 줄이 |---|---|
        if line.lstrip().startswith("|") and i + 1 < len(lines) \
                and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            flush()
            rows = []
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append([strip_inline(c) for c in header])
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                rows.append([strip_inline(c) for c in cells])
                j += 1
            ncol = max(len(r) for r in rows)
            rows = [r + [""] * (ncol - len(r)) for r in rows]
            blocks.append(Block("table", rows=rows, has_header=True,
                                source_line=i + 1))
            i = j
            continue

        m = BULLET.match(line) or NUMBERED.match(line)
        if m:
            flush()
            blocks.append(Block("bullet", strip_inline(m.group(2)),
                                level=_bullet_level(m.group(1)),
                                source_line=i + 1))
            i += 1
            continue

        para_buf.append(line.strip())
        i += 1

    flush()
    return blocks


def placeholders(blocks: list[Block]) -> list[Block]:
    return [b for b in blocks if b.kind in ("figure", "table_ref")]


def find_unresolved(text: str) -> list[str]:
    """최종 산출물에 남으면 안 되는 플레이스홀더 문자열."""
    return [f"{k}-{n}" for k, n in FIG_LINE.findall(text)[:0]] + \
           [f"{m[0]}-{m[1]}" for m in FIG_INLINE.findall(text)]
