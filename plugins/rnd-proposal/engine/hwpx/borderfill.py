# -*- coding: utf-8 -*-
"""표 셀 테두리 — spec ↔ id 역인덱스 + 존 규칙.

★ 중요한 한계 (docs/hwpx_format_notes.md §7):
존 규칙은 **원본 표를 재현하지 못한다** (샘플 양식 표1 15/30, 표2 3/6).
원본에는 회색 stub 라벨열이 있고 두 표가 서로 불일치한다 — 수작업 편집 흔적이라
규칙으로 환원되지 않는다.

그러나 **우리가 생성하는 stub 없는 단순 표**에는 완전히 성립한다. 가상 4×4에
적용하면 필요한 조합이 전부 기존 borderFill에 존재한다(미존재 0건):
    r0: 13 14 14 15    r1: 16 12 12 12    r2: 17 11 11 11    r3: 17 11 11 11
→ {11,12,13,14,15,16,17} 7개만으로 header.xml 무수정 렌더가 성립한다.

**절대 새 borderFill을 header.xml에 추가하지 않는다.** 조회 실패 시 폴백 + 경고.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .consts import BORDER_INNER, BORDER_OUTER, HEADER_FILL, zone_spec
from .header_index import HeaderIndex


def _mm(w: str | None) -> float:
    """'0.15 mm' → 0.15. 정렬용."""
    try:
        return float(str(w).split()[0])
    except (ValueError, IndexError, AttributeError):
        return 99.0


@dataclass
class ZoneResult:
    grid: dict[tuple[int, int], str]     # (row, col) → borderFill id
    fallbacks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BorderFillResolver:
    """spec → id 조회기. 인덱스에 없으면 단계적으로 폴백한다."""

    def __init__(self, hidx: HeaderIndex, stub_cols: int = 0,
                 table_border_fill: str | None = None):
        self.hidx = hidx
        self.stub_cols = stub_cols
        self._index: dict[tuple, str] = {}
        for bid in sorted(hidx.border_fill, key=int):
            self._index.setdefault(hidx.border_fill[bid].spec(), bid)

        # 폴백용 기본 셀. **절대 None을 돌려주면 안 된다** —
        # 셀에 borderFillIDRef가 없으면 문서가 깨진다.
        # 양식마다 선 두께가 다르므로(1번 양식 0.15mm, 2번 양식 0.1mm)
        # 특정 수치를 고정으로 찾으면 안 된다.
        self._plain = self._index.get(
            (BORDER_INNER, BORDER_INNER, BORDER_INNER, BORDER_INNER, None))
        if not self._plain:
            # 채움 없고 네 변 두께가 같은 것 중 가장 얇은 것
            uniform = [
                (b.left, bid) for bid, b in hidx.border_fill.items()
                if b.fill is None and b.left and
                b.left == b.right == b.top == b.bottom]
            if uniform:
                self._plain = sorted(uniform, key=lambda x: (_mm(x[0]), int(x[1])))[0][1]
        if not self._plain and table_border_fill in hidx.border_fill:
            self._plain = table_border_fill
        if not self._plain and hidx.border_fill:
            self._plain = sorted(hidx.border_fill, key=int)[0]

    def default_id(self) -> str | None:
        """이 양식에서 안전하게 쓸 수 있는 borderFill id."""
        return self._plain

    def lookup(self, spec: dict) -> tuple[str | None, str | None]:
        """(id, fallback_reason). id가 None이면 안 된다."""
        key = (spec["l"], spec["r"], spec["t"], spec["b"], spec["fill"])
        if key in self._index:
            return self._index[key], None
        # 1차: 채움 무시
        key2 = (spec["l"], spec["r"], spec["t"], spec["b"], None)
        if key2 in self._index:
            return self._index[key2], f"채움({spec['fill']}) 조합 없음 → 무채움으로 대체"
        # 2차: 두께 조합 무시, 채움만 맞춰 본다 (머리행 음영 보존)
        if spec["fill"]:
            same_fill = [bid for bid, b in self.hidx.border_fill.items()
                         if b.fill == spec["fill"]]
            if same_fill:
                bid = sorted(same_fill, key=int)[0]
                return bid, (f"두께 조합 없음 → 같은 채움({spec['fill']})의 "
                             f"borderFill {bid}로 대체")
        # 3차: 점수 기반 근사 — 이 양식이 가진 것 중 표준 스타일에 가장 가까운 것
        best = self._approximate(spec)
        if best:
            bid, why = best
            return bid, (f"조합 {key} 없음 → 이 양식에서 가장 가까운 "
                         f"borderFill {bid}로 근사 ({why})")
        # 4차: 기본 셀
        if self._plain:
            return self._plain, (f"조합 {key} 없음 → 이 양식의 기본 셀 "
                                 f"{self._plain}로 대체")
        return None, f"조합 {key} 없음, 이 양식에 borderFill이 하나도 없다"

    def _approximate(self, spec: dict):
        """양식이 가진 borderFill 중 목표 spec에 가장 가까운 것을 고른다.

        표준 표 스타일(회색 머리행 + 두께 대비)을 그대로 못 만드는 양식에서도
        '가진 것 중 최선'을 쓴다. 채움 일치를 두께 일치보다 크게 본다 —
        머리행 음영이 표의 가독성에 더 크게 기여하기 때문이다.
        """
        if not self.hidx.border_fill:
            return None
        want_fill = spec.get("fill")
        cands = []
        for bid, b in self.hidx.border_fill.items():
            s = 0.0
            why = []
            if want_fill:
                if b.fill == want_fill:
                    s += 100; why.append("채움 일치")
                elif b.fill:
                    s += 40; why.append(f"채움 있음({b.fill})")
            else:
                if not b.fill:
                    s += 100; why.append("무채움 일치")
            for side in ("l", "r", "t", "b"):
                got = {"l": b.left, "r": b.right, "t": b.top, "b": b.bottom}[side]
                if got == spec[side]:
                    s += 10
                elif got:
                    s += max(0.0, 8 - abs(_mm(got) - _mm(spec[side])) * 20)
            cands.append((s, -int(bid), bid, ", ".join(why) or "두께 근사"))
        cands.sort(reverse=True)
        if not cands or cands[0][0] <= 0:
            return None
        return cands[0][2], cands[0][3]

    def grid(self, nrow: int, ncol: int) -> ZoneResult:
        """표 하나 전체의 셀 borderFill 격자."""
        res = ZoneResult(grid={})
        for r in range(nrow):
            for c in range(ncol):
                spec = zone_spec(r, c, ncol)
                if self.stub_cols and c < self.stub_cols and r > 0:
                    spec["fill"] = HEADER_FILL
                    if c == self.stub_cols - 1:
                        spec["r"] = BORDER_OUTER
                bid, reason = self.lookup(spec)
                if bid is None:
                    res.warnings.append(f"(r{r},c{c}) borderFill 조회 실패: {reason}")
                    continue
                res.grid[(r, c)] = bid
                if reason:
                    res.fallbacks.append(f"(r{r},c{c}) {reason}")
        return res


def self_check(hidx: HeaderIndex, observed_tables: list[dict]) -> dict:
    """원본 표에 존 규칙을 적용해 몇 %가 맞는지 측정한다.

    이 값은 profile의 신뢰도 근거이자 extract_report의 경고 재료다.
    100%를 기대하면 안 된다 — 샘플 양식은 50%다.
    """
    resolver = BorderFillResolver(hidx)
    out = []
    for i, tb in enumerate(observed_tables):
        nrow, ncol = tb["rows"], tb["cols"]
        hit = miss = 0
        examples = []
        for (r, c), cell in tb["cells"].items():
            bid, _ = resolver.lookup(zone_spec(r, c, ncol))
            if bid == cell["border_fill"]:
                hit += 1
            else:
                miss += 1
                if len(examples) < 4:
                    examples.append(f"(r{r},c{c}) 원본={cell['border_fill']} 규칙={bid}")
        total = hit + miss
        # 머리행 제외 전 행이 회색인 열 = stub 블록
        fills = {}
        for (r, c), cell in tb["cells"].items():
            bf = hidx.border_fill.get(cell["border_fill"])
            fills[(r, c)] = bf.fill if bf else None
        stub = [c for c in range(ncol)
                if all(fills.get((r, c)) == HEADER_FILL for r in range(1, nrow))]
        out.append({"table": i + 1, "size": f"{nrow}x{ncol}",
                    "match": hit, "total": total,
                    "rate": round(hit / total * 100, 1) if total else 0.0,
                    "stub_cols": stub, "examples": examples})
    return {"tables": out,
            "note": ("존 규칙은 우리가 생성할 stub 없는 표용이다. "
                     "원본 재현율이 낮은 것은 정상이며, stub 열과 수작업 편집 때문이다.")}


def index_for_profile(hidx: HeaderIndex) -> list[dict]:
    """profile.yaml에 실을 spec→id 역인덱스."""
    rows = []
    for bid in sorted(hidx.border_fill, key=int):
        b = hidx.border_fill[bid]
        rows.append({"id": bid, "l": b.left, "r": b.right,
                     "t": b.top, "b": b.bottom, "fill": b.fill})
    return rows
