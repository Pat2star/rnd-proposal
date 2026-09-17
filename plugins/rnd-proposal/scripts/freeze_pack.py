# -*- coding: utf-8 -*-
"""근거팩 동결 — 하네스 규율 R9 (Phase 2.5).

    python $CLAUDE_PLUGIN_ROOT/scripts/freeze_pack.py --ws workspace/ai-refrigerant/_ws

조사 산출물을 `evidence_pack/` 으로 복사하고 SHA-256 을 기록한다.
이후 작성 실행은 **팩만 입력으로 받고 웹 검색을 하지 않는다.**

## 왜 필요한가 (원 저작자 실측, reproducibility.md §R9)

> 같은 과제명 3회 완전 독립 실행: 문서 구조 1.00 · 골격 100% 일치 · 게이트 전항 PASS
> 인데도 계획서 서술 유사도는 **0.58~0.63** 에 머물렀다. 원인은 작성이 아니라 **조사**다.
> 웹 검색은 비결정적이라 같은 질의도 실행마다 다른 결과를 준다.
> 이 층을 그대로 두면 어떤 규율을 더해도 유사도 상한이 0.6 대에 걸린다.

이 저장소 실측(2026-08-26, 팩 없이 3회): **L6 결론 최저 0.57** — 그 기준선과 일치했다.

## ★ 이 저장소가 한 단계 더 넣은 것 — 동결 **전** 축 간 상충 점검

원 하네스의 Phase 2.5 는 파일을 복사하고 해시를 찍는다. 그런데 **조사 축끼리
모순된 채로 동결되면 그 모순이 3회 실행에 그대로 복제된다.**

실측 근거 두 건:
  · `hthp-2027` R1 — 기술동향과 특허가 정면 상충했는데 대조 없이 한쪽만 채택했고,
    평가위원 2인이 독립적으로 적발했다. 문서 안에 모순이 남았다.
  · 이번 AI냉매 실행 — 정책 축이 기술동향 축의 `Federal Register 2025-19812` 를
    **「Proposed Rule 이라 시행 중인 규제가 아니다」** 로 정정했다.
    동결 전에 잡지 않으면 3회 전부가 틀린 값을 인쇄한다.

그래서 `--require-conflicts` 를 기본값으로 두고, 상충 정리 파일이 없으면 **거부**한다.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import sys

AXIS_PREFIXES = ("10_", "11_", "12_", "13_", "14_")
CONFLICT_NAMES = ("15_axis_conflicts.md", "15_상충확정.md")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws", required=True, help="조사 산출물이 있는 워크스페이스")
    ap.add_argument("--out", help="팩 경로 (기본: <ws>/evidence_pack)")
    ap.add_argument("--allow-missing-conflicts", action="store_true",
                    help="축 간 상충 정리 파일 없이도 동결한다 (권장하지 않음)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ws = os.path.abspath(a.ws)
    pack = os.path.abspath(a.out or os.path.join(ws, "evidence_pack"))

    files = sorted(f for f in os.listdir(ws)
                   if f.endswith(".md") and f.startswith(AXIS_PREFIXES))
    if not files:
        print(f"조사 산출물이 없다: {ws}")
        return 2

    has_conflict = any(os.path.exists(os.path.join(ws, n)) for n in CONFLICT_NAMES)
    if not has_conflict and not a.allow_missing_conflicts:
        print("=" * 70)
        print("동결 거부 — 축 간 상충 정리 파일이 없다")
        print("=" * 70)
        print(f"  다음 중 하나가 필요하다: {' 또는 '.join(CONFLICT_NAMES)}")
        print()
        print("  조사 축끼리 모순된 채로 동결하면 그 모순이 3회 실행에 그대로 복제된다.")
        print("  실측: 정책 축이 기술동향 축의 출처 계층 오기를 정정했다")
        print("        (Federal Register 2025-19812 = Proposed Rule, 시행 중 아님).")
        print("  동결 전에 잡지 않으면 세 판 전부가 틀린 값을 인쇄한다.")
        print()
        print("  정말 건너뛰려면 --allow-missing-conflicts")
        return 2

    os.makedirs(pack, exist_ok=True)
    copied = []
    for f in files + [n for n in CONFLICT_NAMES
                      if os.path.exists(os.path.join(ws, n))]:
        src, dst = os.path.join(ws, f), os.path.join(pack, f)
        shutil.copy2(src, dst)
        copied.append(f)

    lines = []
    for f in sorted(copied):
        lines.append(f"{sha256(os.path.join(pack, f))}  {f}")
    manifest = os.path.join(pack, "PACK.sha256")
    io.open(manifest, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    pack_hash = hashlib.sha256(
        "\n".join(lines).encode("utf-8")).hexdigest()
    io.open(os.path.join(pack, "PACK.id"), "w", encoding="utf-8").write(
        pack_hash + "\n")

    print("=" * 70)
    print(f"근거팩 동결 — {pack}")
    print("=" * 70)
    for ln in lines:
        print("  " + ln[:16] + "  " + ln.split("  ", 1)[1])
    print()
    print(f"  팩 ID (전체 해시): {pack_hash[:32]}")
    print(f"  상충 정리: {'포함' if has_conflict else '★ 없음 (강제 동결)'}")
    print()
    print("  이후 작성 실행은 이 팩만 본다. 웹 검색 금지.")
    print("  계획서 매니페스트에 팩 ID 를 적어라 — 어떤 근거로 쓴 문서인지 증명한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
