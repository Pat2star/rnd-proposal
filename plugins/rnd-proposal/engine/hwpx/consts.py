# -*- coding: utf-8 -*-
"""HWPX 포맷 상수 — 전부 실측으로 확인된 값이다.

각 상수의 근거는 docs/hwpx_format_notes.md 와 tests/test_form_facts.py 에 있다.
추측으로 값을 추가하지 말 것. 추가하려면 먼저 골든 테스트를 쓸 것.
"""
import math

# ── XML 네임스페이스 ────────────────────────────────────────────────
NS = {
    'hp':  'http://www.hancom.co.kr/hwpml/2011/paragraph',
    'hh':  'http://www.hancom.co.kr/hwpml/2011/head',
    'hc':  'http://www.hancom.co.kr/hwpml/2011/core',
    'hs':  'http://www.hancom.co.kr/hwpml/2011/section',
    'hpf': 'http://www.hancom.co.kr/schema/2011/hpf',
    'opf': 'http://www.idpf.org/2007/opf/',
    'ha':  'http://www.hancom.co.kr/hwpml/2011/app',
    'hm':  'http://www.hancom.co.kr/hwpml/2011/master-page',
}

MIMETYPE = "application/hwp+zip"

# ── 단위 환산 ───────────────────────────────────────────────────────
HWPUNIT_PER_MM = 283.465          # 1mm = 283.465 HWPUNIT
HWPUNIT_PER_INCH = 7200

# hp:imgDim 은 96 DPI 기준: dim = px * 7200/96 = px * 75
# 실측 교차검증 2건 (test_form_facts.py::test_imgdim_75):
#   샘플 양식 image1     1508x520  -> imgDim 113100x39000  (113100/1508 = 75.0)
#   test_with_images     3570x2070 -> imgDim 267750x155250 (267750/3570 = 75.0)
HWPUNIT_PER_PX96 = 75

# hp:orgSz 는 PNG에 기록된 DPI 기준 (dpi 미기재 시 96 가정)
#   샘플 양식 image1: 1508 * 7200 / 72390  = 150 DPI
#   test_with_images: 3570 * 7200 / 128520 = 200 DPI


def px_to_orgsz(px: int, dpi: int = 96) -> int:
    """PNG 픽셀 -> hp:orgSz HWPUNIT."""
    return round(px * HWPUNIT_PER_INCH / dpi)


def px_to_imgdim(px: int) -> int:
    """PNG 픽셀 -> hp:imgDim HWPUNIT (항상 96 DPI 기준)."""
    return px * HWPUNIT_PER_PX96


# ── linesegarray ───────────────────────────────────────────────────
# ★ 검증 루프에서 정정된 부분. 두 공식 모두 문단 96개 전수 위반 0건.
BASELINE_RATIO = 0.85

# 한글은 half-up 반올림을 쓴다. 파이썬 내장 round()는 banker's rounding이라
# 17410 * 0.85 = 14798.5 에서 14798 을 내는데 한글 실측값은 14799 다.
# 텍스트 문단은 vertsize 가 작아 .5 가 안 나오므로 이 차이가 안 드러나고,
# 표/그림 앵커 문단(vertsize = 객체 높이)에서만 노출된다.
def half_up(x: float) -> int:
    """한글식 half-up 반올림. 절대 내장 round()로 바꾸지 말 것."""
    return math.floor(x + 0.5)


def lineseg_baseline(vertsize: int) -> int:
    """baseline = half_up(vertsize * 0.85). 고유 조합 8종 전부 일치."""
    return half_up(vertsize * BASELINE_RATIO)


def lineseg_spacing(char_height: int, line_spacing_pct: int) -> int:
    """spacing 의 기준은 vertsize 가 아니라 그 문단의 **글자 높이**다.

    텍스트 문단은 vertsize == char_height 라 두 해석이 우연히 일치하지만,
    표/그림 앵커 문단은 vertsize 가 객체 높이라 갈라진다.
      paraPr 35 (표, vertsize 24390) spacing 880 = 1100 * 0.8   <- charPr 32 height
      paraPr 37 (그림, vertsize 17410) spacing 880 = 1100 * 0.8
      paraPr 16 (표, vertsize 11681) spacing 600 = 1500 * 0.4   <- charPr 10 height
    """
    return half_up(char_height * (line_spacing_pct - 100) / 100)


# 실측 2종뿐: heading.type == NONE -> 393216(0x60000), BULLET -> 2490368(0x260000)
LINESEG_FLAGS_NORMAL = 393216
LINESEG_FLAGS_BULLET = 2490368


# ── ZIP 패키징 ──────────────────────────────────────────────────────
# 샘플 양식 실측 압축 방식. mimetype 은 반드시 0번째 + STORED.
ZIP_STORED_ENTRIES = {
    "mimetype",
    "version.xml",
    "Preview/PrvImage.png",
}   # BinData/*.PNG 도 STORED (PNG는 이미 압축됨)

# ── 표 ─────────────────────────────────────────────────────────────
# borderFill id 는 1-base 다 (1~25, 0번 없음). 검증기가 0을 유효로 보면 오탐한다.
BORDERFILL_MIN_ID = 1

BORDER_OUTER = "0.3 mm"
BORDER_INNER = "0.15 mm"
HEADER_FILL = "#D6D6D6"

# ── 표준 표 스타일 ─────────────────────────────────────────────────
# 양식이나 작성지침에 표 얘기가 없을 때 기준으로 삼는 모양.
# 정부 연구계획서 관행이자 샘플 양식(strategic-2027)의 실제 표 스타일이다.
#   바깥 테두리 0.3mm / 안쪽 0.15mm / 머리행 회색 #D6D6D6 / 표 외곽 0.12mm
# 양식이 이 조합을 갖고 있지 않으면 가진 것 중 가장 가까운 것으로 근사한다
# (borderfill.BorderFillResolver 의 점수 기반 근사).
DEFAULT_TABLE_STYLE = {
    "outer": BORDER_OUTER,
    "inner": BORDER_INNER,
    "header_fill": HEADER_FILL,
    "tbl_border": "0.12 mm",
    "in_margin": {"left": 510, "right": 510, "top": 141, "bottom": 141},
    "cell_margin": {"left": 600, "right": 600, "top": 400, "bottom": 400},
    "default_row_height": 1386,
    "repeat_header": 1,
    "page_break": "CELL",
    "cell_spacing": 0,
}


def zone_spec(row: int, col: int, ncol: int):
    """stub 열이 없는 단순 표의 셀 테두리 spec.

    ★ 주의: 이 규칙은 '우리가 생성하는 표'에만 유효하다.
    샘플 양식의 원본 표는 회색 stub 라벨열(연도/단계)이 있고 두 표가 서로
    불일치(수작업 편집 흔적)해서 이 규칙으로 재현되지 않는다 (15/30, 3/6).

    stub 없는 가상 4x4 표에 적용하면 필요한 조합이 전부 기존 borderFill 에
    존재한다 (미존재 0건) -> header.xml 무수정 렌더가 성립한다:
        r0: 13 14 14 15
        r1: 16 12 12 12
        r2: 17 11 11 11
        r3: 17 11 11 11
    """
    return {
        'l':    BORDER_OUTER if col == 0 else BORDER_INNER,
        'r':    BORDER_OUTER if (col == ncol - 1 and row == 0) else BORDER_INNER,
        't':    BORDER_OUTER if row <= 1 else BORDER_INNER,
        'b':    BORDER_OUTER if row == 0 else BORDER_INNER,
        'fill': HEADER_FILL if row == 0 else None,
    }


# ── 그림 캔버스 -> HWPX curSz 상수표 ───────────────────────────────
# 본문폭을 100% 쓸 때의 높이. AR 이 캔버스로 고정되므로 상수가 된다.
CANVAS_AR = {
    'wide': 16 / 9,      # 1600x900
    'band': 2.5,         # 1600x640
    'hero': 1.6,         # 1600x1000
    'tall': 0.8,         # 1200x1500
}


def cursz(text_width: int, ar: float, width_pct: float = 1.0):
    """(curSz_w, curSz_h) 계산. text_width 는 profile.page.text_width."""
    w = round(text_width * width_pct)
    return w, round(w / ar)
