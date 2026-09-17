# -*- coding: utf-8 -*-
"""요청하지 않은 그림이 원고에 들어갔는가.

    python $CLAUDE_PLUGIN_ROOT/scripts/check_figures.py --md <원고.md> --requirements <requirements.md>

## 왜 필요한가 (2026-09-17 사용자 지시)

다른 PC 에서 「300℃급 공기 사이클 히트펌프 10쪽」을 만들었더니 **그림을 요청하지
않았는데 두 장이 들어갔다**(개괄도·조직도). SETUP.md 는 「그림 종류를 안 주면
그림 없이 진행」이라고 약속했지만 **오케스트레이터 어디에도 그 조건이 없었고**,
인터뷰어는 오히려 「에너지 시스템이면 개괄도가 핵심이므로 반드시 물어라」고 그림을
권하고 있었다. 약속은 문서에만 있고 아무도 재지 않았다.

사용자 규칙: **그림은 사용자가 요청할 때만 넣는다.**

## 선언 형식

requirements.md 프런트매터에 한 줄.

    figures: [system, org, gantt]     # 요청한 그림
    figures: []                       # 요청 없음

**선언이 없으면 요청이 없는 것으로 본다.** 기본값이 「끔」이다.

판정은 **개수**로 한다 — 원고의 그림 수가 선언한 수보다 많으면 위반이다.
종류 이름은 사람마다 달리 적어서(「개요도」·「system」·「사이클도」) 맞대기 어렵다.

exit 0 통과 · exit 2 위반.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

IMG = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
# 양식 엔진 경로(engine.hwpx.build_hwpx)는 독립된 한 줄 `[FIG-1: 제목]` 을 그림으로 본다.
# 두 조립 경로를 다 막아야 한다 — 이번 실측 산출물은 이쪽 경로를 탔다.
FIG_BLOCK = re.compile(r"^\s*\[FIG-(\d+)\s*:\s*(.+?)\s*\]\s*$", re.M)
FRONT = re.compile(r"\A---\s*\n(.*?)\n---", re.S)
FIG_LINE = re.compile(r"^figures\s*:\s*(.*)$", re.M)


def requested(req_path: str | None) -> tuple[list[str], str]:
    """(요청한 그림 목록, 근거 설명). 선언이 없으면 빈 목록."""
    if not req_path or not os.path.exists(req_path):
        return [], "requirements.md 없음 → 요청 없음으로 본다"
    text = open(req_path, encoding="utf-8").read()
    m = FRONT.match(text)
    line = FIG_LINE.search(m.group(1)) if m else None
    if not line:
        return [], "figures: 선언 없음 → 요청 없음으로 본다"
    raw = line.group(1).strip()
    if raw in ("", "[]", "없음", "none", "None", "-"):
        return [], "figures: 비어 있음"
    items = [x.strip().strip("'\"") for x in raw.strip("[]").split(",")]
    items = [x for x in items if x]
    return items, f"figures: {items}"


def images_in(md_path: str) -> list[str]:
    text = open(md_path, encoding="utf-8").read()
    return IMG.findall(text) + [f"FIG-{n}: {t}" for n, t in FIG_BLOCK.findall(text)]


def find_requirements(md_path: str, depth: int = 3) -> str | None:
    """원고 위쪽으로 올라가며 requirements.md 를 찾는다(원고가 build/ 에 있을 수 있다)."""
    d = os.path.dirname(os.path.abspath(md_path))
    for _ in range(depth + 1):
        q = os.path.join(d, "requirements.md")
        if os.path.exists(q):
            return q
        d = os.path.dirname(d)
    return None


def check(md_path: str, req_path: str | None) -> tuple[bool, str]:
    want, why = requested(req_path)
    got = images_in(md_path)
    ok = len(got) <= len(want)
    lines = [f"  요청  {len(want)}장   ({why})",
             f"  원고  {len(got)}장   {got if got else ''}"]
    if not ok:
        lines.append(f"FAIL — 요청하지 않은 그림 {len(got) - len(want)}장. "
                     "그림은 사용자가 요청할 때만 넣는다.")
    else:
        lines.append("PASS")
    return ok, "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True)
    ap.add_argument("--requirements")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("그림 검사 — 요청한 것만 들어갔는가")
    ok, msg = check(a.md, a.requirements or find_requirements(a.md))
    print(msg)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
