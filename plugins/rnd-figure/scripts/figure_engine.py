"""
Figure Engine v2: HTML/CSS → PNG 렌더링 (Playwright).
matplotlib 폴백 지원.

Usage:
    # HTML 렌더링 (기본)
    python figure_engine.py --type timeline --data data.json --output fig.png

    # matplotlib 폴백
    python figure_engine.py --type timeline --data data.json --output fig.png --backend mpl

    # 등록된 템플릿 목록
    python figure_engine.py --list
"""

import json
import argparse
import sys
import os

# ── Academic Color Themes ──
# 학술 논문에서 가장 많이 쓰이는 5가지 색 조합
THEMES = {
    'nature': {
        'name': 'Nature (기본)',
        'colors': [
            ('#E64B35', '#E64B35CC'),  # 적색
            ('#4DBBD5', '#4DBBD5CC'),  # 청록
            ('#00A087', '#00A087CC'),  # 녹색
            ('#3C5488', '#3C5488CC'),  # 남색
            ('#F39B7F', '#F39B7FCC'),  # 살구
            ('#8491B4', '#8491B4CC'),  # 회청
            ('#91D1C2', '#91D1C2CC'),  # 민트
            ('#DC9E82', '#DC9E82CC'),  # 황토
        ],
        'primary': '#3C5488', 'primary_light': '#4A6AA5',
        'accent': '#E64B35', 'accent_light': '#F06050',
        'title': '#2C3E50',
    },
    'ieee': {
        'name': 'IEEE',
        'colors': [
            ('#0072B2', '#0072B2CC'),  # 진파랑
            ('#D55E00', '#D55E00CC'),  # 주황
            ('#009E73', '#009E73CC'),  # 청록
            ('#CC79A7', '#CC79A7CC'),  # 분홍
            ('#F0E442', '#E8DC3A'),    # 노랑
            ('#56B4E9', '#56B4E9CC'),  # 하늘
            ('#E69F00', '#E69F00CC'),  # 금색
            ('#999999', '#999999CC'),  # 회색
        ],
        'primary': '#0072B2', 'primary_light': '#1A8AC4',
        'accent': '#D55E00', 'accent_light': '#E06A10',
        'title': '#1A1A2E',
    },
    'lancet': {
        'name': 'Lancet',
        'colors': [
            ('#00468B', '#00468BCC'),  # 네이비
            ('#ED0000', '#ED0000CC'),  # 빨강
            ('#42B540', '#42B540CC'),  # 녹색
            ('#0099B4', '#0099B4CC'),  # 청록
            ('#925E9F', '#925E9FCC'),  # 보라
            ('#FDAF91', '#FDAF91CC'),  # 살구
            ('#AD002A', '#AD002ACC'),  # 적갈
            ('#ADB6B6', '#ADB6B6CC'),  # 회색
        ],
        'primary': '#00468B', 'primary_light': '#1A5A9E',
        'accent': '#ED0000', 'accent_light': '#FF1A1A',
        'title': '#1A1A2E',
    },
    'aaas': {
        'name': 'AAAS/Science',
        'colors': [
            ('#3B4992', '#3B4992CC'),  # 진파랑
            ('#EE0000', '#EE0000CC'),  # 빨강
            ('#008B45', '#008B45CC'),  # 녹색
            ('#631879', '#631879CC'),  # 보라
            ('#008280', '#008280CC'),  # 청록
            ('#BB0021', '#BB0021CC'),  # 적갈
            ('#5F559B', '#5F559BCC'),  # 연보라
            ('#A20056', '#A20056CC'),  # 자홍
        ],
        'primary': '#3B4992', 'primary_light': '#4D5BA6',
        'accent': '#EE0000', 'accent_light': '#FF2222',
        'title': '#1A1A2E',
    },
    'nejm': {
        'name': 'NEJM',
        'colors': [
            ('#BC3C29', '#BC3C29CC'),  # 적갈
            ('#0072B5', '#0072B5CC'),  # 파랑
            ('#E18727', '#E18727CC'),  # 주황
            ('#20854E', '#20854ECC'),  # 녹색
            ('#7876B1', '#7876B1CC'),  # 회보라
            ('#6F99AD', '#6F99ADCC'),  # 회청
            ('#FFDC91', '#F5D080'),    # 금색
            ('#EE4C97', '#EE4C97CC'),  # 핑크
        ],
        'primary': '#0072B5', 'primary_light': '#1A84C7',
        'accent': '#BC3C29', 'accent_light': '#D04A37',
        'title': '#1A1A2E',
    },
}

# ── Active theme (default: nature) ──
_current_theme = 'nature'


def set_theme(theme_name):
    """Set the active color theme. Available: nature, ieee, lancet, aaas, nejm"""
    global _current_theme, P, COLOR_PAIRS
    if theme_name not in THEMES:
        raise ValueError(f"Unknown theme '{theme_name}'. Available: {', '.join(THEMES.keys())}")
    _current_theme = theme_name
    _apply_theme()


def _apply_theme():
    global P, COLOR_PAIRS
    t = THEMES[_current_theme]
    P.update({
        'primary': t['primary'], 'primary_light': t['primary_light'],
        'accent': t['accent'], 'accent_light': t['accent_light'],
        'title': t['title'],
    })
    COLOR_PAIRS[:] = t['colors']


P = {
    'bg':           '#FFFFFF',
    'text_dark':    '#1A1A2E',
    'text_mid':     '#6B7B8D',
    'text_light':   '#FFFFFF',
    'border':       '#E2E8F0',
    'row_alt':      '#F8FAFC',
    # theme-dependent (set by _apply_theme)
    'primary':      '', 'primary_light': '',
    'accent':       '', 'accent_light': '',
    'title':        '',
}

COLOR_PAIRS = []
_apply_theme()  # initialize with default theme

# ── Icon Auto-Detection ──

_ICON_MAP = {
    # 문서/파일
    'pdf': 'fa-file-pdf', '논문': 'fa-file-pdf', 'paper': 'fa-file-pdf',
    '문서': 'fa-file-lines', 'doc': 'fa-file-lines', '보고서': 'fa-file-lines',
    # 데이터
    'db': 'fa-database', 'database': 'fa-database', '데이터': 'fa-database',
    '벡터': 'fa-cubes', '임베딩': 'fa-cubes', 'embedding': 'fa-cubes',
    '저장': 'fa-floppy-disk', '캐시': 'fa-box-archive',
    # 웹/네트워크
    'web': 'fa-globe', '웹': 'fa-globe', '크롤링': 'fa-spider',
    'api': 'fa-plug', '서버': 'fa-server', 'server': 'fa-server',
    'ui': 'fa-desktop', '인터페이스': 'fa-display',
    '챗봇': 'fa-comments', 'chat': 'fa-comments',
    '네트워크': 'fa-network-wired', '클라우드': 'fa-cloud',
    # AI/ML
    'ai': 'fa-brain', 'ml': 'fa-brain', '모델': 'fa-brain',
    'llm': 'fa-robot', '추론': 'fa-lightbulb', '생성': 'fa-wand-magic-sparkles',
    '학습': 'fa-graduation-cap', '훈련': 'fa-dumbbell', 'training': 'fa-dumbbell',
    '파인튜닝': 'fa-sliders', 'fine': 'fa-sliders',
    # 처리/분석
    '검색': 'fa-magnifying-glass', 'search': 'fa-magnifying-glass',
    '처리': 'fa-gears', '전처리': 'fa-filter', '필터': 'fa-filter',
    '분석': 'fa-chart-bar', '시각화': 'fa-chart-line', '평가': 'fa-chart-pie',
    '청킹': 'fa-scissors', '분할': 'fa-scissors',
    '리랭킹': 'fa-ranking-star', '랭킹': 'fa-ranking-star',
    '압축': 'fa-compress', '변환': 'fa-arrows-rotate',
    # 프롬프트/텍스트
    '프롬프트': 'fa-terminal', '출처': 'fa-quote-right',
    '텍스트': 'fa-font', '요약': 'fa-align-left',
    # 보안/인증
    '보안': 'fa-shield-halved', '인증': 'fa-key', '검증': 'fa-circle-check',
    # 하드웨어
    '센서': 'fa-microchip', '카메라': 'fa-camera', 'gpu': 'fa-microchip',
    # 일반
    '사용자': 'fa-user', 'user': 'fa-user',
    '출력': 'fa-arrow-right-from-bracket', '입력': 'fa-arrow-right-to-bracket',
    '설정': 'fa-gear', '관리': 'fa-toolbox',
    '교통': 'fa-car', '에너지': 'fa-bolt', '안전': 'fa-shield',
    '환경': 'fa-leaf', '도킹': 'fa-link', '실험': 'fa-flask',
    '약물': 'fa-pills', '독성': 'fa-skull-crossbones',
    '최적화': 'fa-bullseye', '스크리닝': 'fa-vials',
    '유전체': 'fa-dna', '타겟': 'fa-crosshairs',
}


def _detect_icon(text):
    """Auto-detect a Font Awesome icon based on text content."""
    text_lower = text.lower()
    for keyword, icon in _ICON_MAP.items():
        if keyword in text_lower:
            return icon
    return 'fa-cube'


# ── Shared HTML parts ──

_FA_CDN = '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">'


def _base_style():
    return f"""
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #FFFFFF;
    font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif;
    color: #1A1A2E;
    -webkit-font-smoothing: antialiased;
}}
.fig-title {{
    text-align: center;
    margin-bottom: 48px;
}}
.fig-title h1 {{
    font-size: 38px;
    font-weight: 900;
    color: {P['title']};
    letter-spacing: -0.5px;
}}
.fig-title p {{
    font-size: 17px;
    color: #6B7B8D;
    margin-top: 8px;
    font-style: italic;
}}
"""

_ARROW_SVG = '<svg viewBox="0 0 50 24" width="50" height="24"><line x1="0" y1="12" x2="38" y2="12" stroke="#CBD5E1" stroke-width="2.5"/><polygon points="38,6 50,12 38,18" fill="#CBD5E1"/></svg>'

_ARROW_DOWN_SVG = '<svg viewBox="0 0 24 40" width="24" height="40"><line x1="12" y1="0" x2="12" y2="30" stroke="#CBD5E1" stroke-width="2.5"/><polygon points="6,30 12,40 18,30" fill="#CBD5E1"/></svg>'


def _gradient(c1, c2, deg=135):
    return f"linear-gradient({deg}deg, {c1}, {c2})"


def _wrap_html(body_content, width=1800, extra_style="", use_fa=False):
    fa_link = _FA_CDN if use_fa else ''
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
{fa_link}
<style>{_base_style()}\n{extra_style}</style>
</head><body style="width:{width}px; padding:50px 70px;">
{body_content}
</body></html>"""


def _render_to_png(html, output, width=1800, wait_selector=None):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 600})
        page.set_content(html)
        page.wait_for_load_state("networkidle")
        if wait_selector:
            page.wait_for_selector(wait_selector, timeout=15000)
            page.wait_for_timeout(500)
        h = page.evaluate("document.body.scrollHeight")
        page.set_viewport_size({"width": width, "height": h})
        page.screenshot(path=output, full_page=True, type="png")
        browser.close()


# ============================================================
# TEMPLATE 1: flowchart
# ============================================================

def render_flowchart(data, output):
    steps = data['steps']
    title = data.get('title', '프로세스 흐름도')
    subtitle = data.get('subtitle', '')

    step_html = []
    for i, step in enumerate(steps):
        c1, c2 = COLOR_PAIRS[i % len(COLOR_PAIRS)]
        icon = _detect_icon(step['label'])
        is_decision = step.get('type') == 'decision'

        if is_decision:
            box = f"""<div class="step">
                <div class="step-box decision" style="background:{_gradient(c1, c2)};">
                    <div class="decision-content">
                        <i class="fa-solid {icon}" style="font-size:16px; opacity:0.85;"></i>
                        <div class="label">{step['label']}</div>
                        <div class="detail">{step.get('detail', '')}</div>
                    </div>
                </div>
                <div class="step-num">STEP {i+1}</div>
            </div>"""
        else:
            box = f"""<div class="step">
                <div class="step-box process" style="background:{_gradient(c1, c2)};">
                    <i class="fa-solid {icon}" style="font-size:18px; opacity:0.85; margin-bottom:4px;"></i>
                    <div class="label">{step['label']}</div>
                    <div class="detail">{step.get('detail', '')}</div>
                </div>
                <div class="step-num">STEP {i+1}</div>
            </div>"""

        step_html.append(box)
        if i < len(steps) - 1:
            step_html.append(f'<div class="arrow">{_ARROW_SVG}</div>')

    style = """
    .pipeline {
        display: flex; align-items: center; justify-content: center;
        padding: 30px 0;
    }
    .step {
        display: flex; flex-direction: column; align-items: center;
        min-width: 220px;
    }
    .step-box {
        width: 220px; height: 130px; border-radius: 16px;
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        color: white;
    }
    .step-box.process { box-shadow: 0 6px 22px rgba(0,0,0,0.14); }
    .step-box.decision {
        width: 130px; height: 130px; border-radius: 16px;
        transform: rotate(45deg);
        box-shadow: 0 6px 22px rgba(0,0,0,0.14);
        margin: 15px 40px;
    }
    .decision-content {
        transform: rotate(-45deg); text-align: center;
    }
    .label { font-size: 18px; font-weight: 700; line-height: 1.3; text-align: center; }
    .detail { font-size: 14px; opacity: 0.85; margin-top: 4px; }
    .step-num {
        font-size: 12px; color: #9BAEBF; font-weight: 700; letter-spacing: 1px;
        margin-top: 16px;
    }
    .arrow { display: flex; align-items: center; padding: 0 10px; }
    """

    sub_html = f'<p>{subtitle}</p>' if subtitle else ''
    body = f"""<div class="fig-title"><h1>{title}</h1>{sub_html}</div>
    <div class="pipeline">{''.join(step_html)}</div>"""

    w = max(1600, len(steps) * 300)
    html = _wrap_html(body, width=w, extra_style=style, use_fa=True)
    _render_to_png(html, output, width=w)


# ============================================================
# TEMPLATE 2: architecture
# ============================================================

def render_architecture(data, output):
    """Architecture diagram with icons and gradient connectors."""
    layers = data['layers']
    title = data.get('title', '시스템 구조도')
    subtitle = data.get('subtitle', '')

    layers_html = []
    for li, layer in enumerate(layers):
        c1, c2 = COLOR_PAIRS[li % len(COLOR_PAIRS)]
        layer_name = layer['name']
        layer_icon = layer.get('icon', _detect_icon(layer_name))

        # Build item pills with auto-detected icons
        items_html = []
        for item in layer['items']:
            if isinstance(item, dict):
                name, icon = item['name'], item.get('icon', _detect_icon(item['name']))
            else:
                name, icon = item, _detect_icon(item)
            items_html.append(f"""
            <div class="a-pill" style="background:{_gradient(c1, c2)};">
                <i class="fas {icon}"></i><span>{name}</span>
            </div>""")

        layers_html.append(f"""
        <div class="a-layer">
            <div class="a-layer-head">
                <div class="a-badge" style="background:{c1};">
                    <i class="fas {layer_icon}"></i>
                </div>
                <span class="a-layer-title">{layer_name}</span>
                <div class="a-badge-line" style="background:{c1};"></div>
            </div>
            <div class="a-items">{''.join(items_html)}</div>
        </div>""")

        if li < len(layers) - 1:
            layers_html.append(f"""
            <div class="a-conn">
                <svg width="60" height="48" viewBox="0 0 60 48">
                    <defs><linearGradient id="cg{li}" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="{c1}" stop-opacity="0.6"/>
                        <stop offset="100%" stop-color="{COLOR_PAIRS[(li+1)%len(COLOR_PAIRS)][0]}" stop-opacity="0.6"/>
                    </linearGradient></defs>
                    <line x1="30" y1="0" x2="30" y2="36" stroke="url(#cg{li})" stroke-width="2.5"/>
                    <polygon points="23,34 30,46 37,34" fill="{COLOR_PAIRS[(li+1)%len(COLOR_PAIRS)][0]}" opacity="0.6"/>
                </svg>
            </div>""")

    style = f"""
    .a-container {{
        display: flex; flex-direction: column; align-items: center; gap: 0;
    }}
    .a-layer {{
        width: 92%;
        background: #F8FAFC;
        border: 1px solid #EDF2F7;
        border-radius: 22px;
        padding: 28px 36px 24px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.05);
    }}
    .a-layer-head {{
        display: flex; align-items: center; gap: 14px;
        margin-bottom: 20px;
    }}
    .a-badge {{
        width: 40px; height: 40px; border-radius: 12px;
        display: flex; align-items: center; justify-content: center;
        color: white; font-size: 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }}
    .a-badge-line {{
        flex: 1; height: 2px; opacity: 0.15; border-radius: 1px;
    }}
    .a-layer-title {{
        font-size: 17px; font-weight: 800; color: {P['title']};
        letter-spacing: -0.3px;
    }}
    .a-items {{
        display: flex; gap: 14px; justify-content: center; flex-wrap: wrap;
    }}
    .a-pill {{
        display: flex; align-items: center; gap: 10px;
        padding: 14px 26px; border-radius: 50px;
        color: white; font-size: 16px; font-weight: 700;
        box-shadow: 0 4px 16px rgba(0,0,0,0.13);
    }}
    .a-pill i {{ font-size: 15px; opacity: 0.9; }}
    .a-conn {{
        display: flex; justify-content: center; padding: 4px 0;
    }}
    """

    sub_html = f'<p>{subtitle}</p>' if subtitle else ''
    body = f"""<div class="fig-title"><h1>{title}</h1>{sub_html}</div>
    <div class="a-container">{''.join(layers_html)}</div>"""

    html = _wrap_html(body, extra_style=style, use_fa=True)
    _render_to_png(html, output, wait_selector='.a-pill')


# ============================================================
# TEMPLATE 3: comparison_table
# ============================================================

def render_comparison_table(data, output):
    headers = data['headers']
    rows = data['rows']
    title = data.get('title', '비교표')
    highlight = data.get('highlight_col', len(headers) - 1)

    # header
    th_html = []
    for j, h in enumerate(headers):
        if j == highlight:
            bg = _gradient(P['accent'], P['accent_light'])
        elif j == 0:
            bg = _gradient(P['primary'], P['primary_light'])
        else:
            cp = COLOR_PAIRS[(j - 1) % len(COLOR_PAIRS)]
            bg = _gradient(cp[0], cp[1])
        th_html.append(f'<th style="background:{bg};">{h}</th>')

    # rows
    tr_html = []
    for i, row in enumerate(rows):
        tds = []
        for j, cell in enumerate(row):
            if j == 0:
                tds.append(f'<td class="row-label">{cell}</td>')
            elif j == highlight:
                tds.append(f'<td class="highlight-cell">{cell}</td>')
            else:
                tds.append(f'<td>{cell}</td>')
        alt = ' class="alt"' if i % 2 == 1 else ''
        tr_html.append(f'<tr{alt}>{"".join(tds)}</tr>')

    style = f"""
    .table-wrap {{ display: flex; justify-content: center; }}
    table {{ border-collapse: separate; border-spacing: 4px; width: 96%; }}
    th {{
        color: white; font-weight: 700; font-size: 17px;
        padding: 18px 24px; border-radius: 10px;
        text-align: center;
        box-shadow: 0 3px 10px rgba(0,0,0,0.12);
    }}
    td {{
        padding: 16px 22px; text-align: center; font-size: 16px;
        border-radius: 8px; background: white;
        border: 1px solid #EDF2F7;
    }}
    tr.alt td {{ background: #F8FAFC; }}
    .row-label {{
        background: {_gradient(P['primary'], P['primary_light'])} !important;
        color: white !important; font-weight: 700;
        border: none !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }}
    .highlight-cell {{
        background: #FFF8F0 !important;
        color: {P['accent']} !important;
        font-weight: 700;
        border: 1.5px solid {P['accent']}30 !important;
    }}
    """

    body = f"""<div class="fig-title"><h1>{title}</h1></div>
    <div class="table-wrap">
    <table><thead><tr>{''.join(th_html)}</tr></thead>
    <tbody>{''.join(tr_html)}</tbody></table>
    </div>"""

    html = _wrap_html(body, extra_style=style)
    _render_to_png(html, output)


# ============================================================
# TEMPLATE 4: timeline
# ============================================================

def render_timeline(data, output):
    tasks = data['tasks']
    total = data.get('total', 12)
    unit = data.get('unit', '월')
    title = data.get('title', '연구 추진일정')

    # group colors
    groups = list(dict.fromkeys(t.get('group', '') for t in tasks))
    group_colors = {g: COLOR_PAIRS[i % len(COLOR_PAIRS)] for i, g in enumerate(groups)}

    # grid columns
    col_template = ' '.join(['1fr'] * total)

    # task bars
    bars_html = []
    for task in tasks:
        c1, c2 = group_colors.get(task.get('group', ''), COLOR_PAIRS[0])
        start = task['start']
        end = task['end']
        bars_html.append(f"""
        <div class="gantt-bar" style="
            grid-column: {start} / {end + 1};
            background: {_gradient(c1, c2, 90)};
        ">{task['name']}</div>""")

    # month labels
    months_html = ''.join(f'<div class="month-label">{i}{unit}</div>' for i in range(1, total + 1))

    # legend
    legend_html = ''.join(
        f'<div class="legend-item"><div class="legend-dot" style="background:{c1};"></div>{g}</div>'
        for g, (c1, c2) in group_colors.items() if g
    )

    style = f"""
    .gantt-grid {{
        display: grid;
        grid-template-columns: {col_template};
        gap: 8px 0;
        padding: 0 20px;
    }}
    .gantt-bar {{
        padding: 14px 18px;
        border-radius: 10px;
        color: white;
        font-size: 16px;
        font-weight: 700;
        text-align: center;
        box-shadow: 0 4px 14px rgba(0,0,0,0.12);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }}
    .month-row {{
        display: grid;
        grid-template-columns: {col_template};
        padding: 0 20px;
        margin-top: 16px;
    }}
    .month-label {{
        text-align: center;
        font-size: 14px;
        color: #9BAEBF;
        font-weight: 500;
    }}
    .legend {{
        display: flex;
        justify-content: center;
        gap: 30px;
        margin-top: 30px;
        padding-top: 16px;
        border-top: 1px solid #EDF2F7;
    }}
    .legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 15px; color: #6B7B8D; }}
    .legend-dot {{ width: 12px; height: 12px; border-radius: 4px; }}
    """

    body = f"""<div class="fig-title"><h1>{title}</h1></div>
    <div class="gantt-grid">{''.join(bars_html)}</div>
    <div class="month-row">{months_html}</div>
    <div class="legend">{legend_html}</div>"""

    html = _wrap_html(body, width=max(1600, total * 100), extra_style=style)
    _render_to_png(html, output, width=max(1600, total * 100))


# ============================================================
# TEMPLATE 5: hierarchy
# ============================================================

def render_hierarchy(data, output):
    """Hierarchy diagram with icons and gradient connectors."""
    root = data['root']
    title = data.get('title', '계층 구조도')

    children = root.get('children', [])
    root_icon = root.get('icon', _detect_icon(root['name']))

    child_blocks = []
    for i, child in enumerate(children):
        cp = COLOR_PAIRS[i % len(COLOR_PAIRS)]
        c1, c2 = cp
        child_icon = child.get('icon', _detect_icon(child['name']))

        gc_html = ''
        if 'children' in child and child['children']:
            gc_items = []
            for gc in child['children']:
                gc_icon = gc.get('icon', _detect_icon(gc['name'])) if isinstance(gc, dict) else _detect_icon(gc)
                gc_name = gc['name'] if isinstance(gc, dict) else gc
                gc_items.append(
                    f'<div class="h-leaf" style="background:{_gradient(c1, c2)}; opacity:0.85;">'
                    f'<i class="fas {gc_icon}"></i>{gc_name}</div>'
                )
            gc_html = f'<div class="h-children">{"".join(gc_items)}</div>'

        child_blocks.append(f"""
        <div class="h-branch">
            <div class="h-node" style="background:{_gradient(c1, c2)};">
                <i class="fas {child_icon}"></i><span>{child['name']}</span>
            </div>
            <div class="h-connector" style="background:linear-gradient(180deg, {c1}40, {c1}10);"></div>
            {gc_html}
        </div>""")

    style = f"""
    .h-tree {{ display: flex; flex-direction: column; align-items: center; gap: 0; }}
    .h-root-connector {{
        width: 3px; height: 44px;
        background: linear-gradient(180deg, {P['primary']}60, {P['primary']}15);
        margin: 0 auto;
    }}
    .h-branches {{
        display: flex; justify-content: center; gap: 56px;
        position: relative; padding-top: 24px;
    }}
    .h-branches::before {{
        content: '';
        position: absolute; top: 0;
        left: 8%; right: 8%;
        height: 2px;
        background: linear-gradient(90deg, transparent, {P['primary']}30, {P['primary']}30, transparent);
    }}
    .h-branch {{
        display: flex; flex-direction: column; align-items: center; gap: 0;
        min-width: 140px;
    }}
    .h-connector {{ width: 3px; height: 36px; border-radius: 2px; }}
    .h-children {{ display: flex; gap: 12px; justify-content: center; margin-top: 6px; }}
    .h-node {{
        display: flex; align-items: center; gap: 10px;
        padding: 16px 30px; border-radius: 14px;
        color: white; font-size: 17px; font-weight: 700;
        box-shadow: 0 6px 20px rgba(0,0,0,0.13);
        text-align: center; white-space: nowrap;
    }}
    .h-node i {{ font-size: 15px; opacity: 0.9; }}
    .h-leaf {{
        display: flex; align-items: center; gap: 8px;
        font-size: 14px; padding: 11px 20px; border-radius: 50px;
        color: white; font-weight: 600;
        box-shadow: 0 4px 14px rgba(0,0,0,0.10);
    }}
    .h-leaf i {{ font-size: 12px; opacity: 0.85; }}
    .h-root-node {{
        display: flex; align-items: center; gap: 12px;
        font-size: 21px; font-weight: 900; padding: 20px 44px;
        border-radius: 18px; color: white;
        background: {_gradient(P['primary'], P['primary_light'])};
        box-shadow: 0 8px 28px rgba(0,0,0,0.16);
    }}
    .h-root-node i {{ font-size: 20px; }}
    """

    root_html = f'<div class="h-root-node"><i class="fas {root_icon}"></i>{root["name"]}</div>'

    body = f"""<div class="fig-title"><h1>{title}</h1></div>
    <div class="h-tree">
        {root_html}
        <div class="h-root-connector"></div>
        <div class="h-branches">{''.join(child_blocks)}</div>
    </div>"""

    html = _wrap_html(body, extra_style=style, use_fa=True)
    _render_to_png(html, output, wait_selector='.h-leaf')


# ============================================================
# TEMPLATE 6: bar_chart
# ============================================================

def render_bar_chart(data, output):
    categories = data['categories']
    series = data['series']
    title = data.get('title', '')
    ylabel = data.get('ylabel', '')
    n_cat = len(categories)
    n_ser = len(series)

    max_val = max(max(s['values']) for s in series)
    scale = 250 / max_val  # max bar height 250px

    # bars per category
    cat_html = []
    for ci, cat in enumerate(categories):
        bars = []
        for si, s in enumerate(series):
            val = s['values'][ci]
            h = val * scale
            c1, c2 = COLOR_PAIRS[si % len(COLOR_PAIRS)]
            bars.append(f"""
            <div class="bar-wrap">
                <div class="bar-value">{val:g}</div>
                <div class="bar" style="height:{h}px; background:{_gradient(c1, c2, 180)};"></div>
            </div>""")
        cat_html.append(f"""
        <div class="bar-group">
            <div class="bars">{''.join(bars)}</div>
            <div class="cat-label">{cat}</div>
        </div>""")

    # legend
    legend = ''.join(
        f'<div class="legend-item"><div class="legend-dot" style="background:{COLOR_PAIRS[i % len(COLOR_PAIRS)][0]};"></div>{s["name"]}</div>'
        for i, s in enumerate(series)
    )

    style = """
    .chart-area { display: flex; justify-content: center; align-items: flex-end; gap: 40px; padding: 20px 40px; }
    .bar-group { display: flex; flex-direction: column; align-items: center; }
    .bars { display: flex; gap: 6px; align-items: flex-end; }
    .bar-wrap { display: flex; flex-direction: column; align-items: center; }
    .bar {
        width: 48px; border-radius: 8px 8px 4px 4px;
        box-shadow: 0 3px 10px rgba(0,0,0,0.1);
        min-height: 4px;
    }
    .bar-value {
        font-size: 15px; font-weight: 700; color: #1B3A5C;
        margin-bottom: 6px;
    }
    .cat-label { font-size: 16px; color: #6B7B8D; margin-top: 12px; font-weight: 500; }
    .chart-ylabel {
        writing-mode: vertical-rl; transform: rotate(180deg);
        font-size: 15px; color: #9BAEBF; margin-right: 10px;
    }
    .legend {
        display: flex; justify-content: center; gap: 30px;
        margin-top: 30px; padding-top: 16px; border-top: 1px solid #EDF2F7;
    }
    .legend-item { display: flex; align-items: center; gap: 6px; font-size: 15px; color: #6B7B8D; }
    .legend-dot { width: 12px; height: 12px; border-radius: 3px; }
    """

    ylabel_html = f'<div class="chart-ylabel">{ylabel}</div>' if ylabel else ''

    body = f"""<div class="fig-title"><h1>{title}</h1></div>
    <div style="display:flex; justify-content:center; align-items:center;">
        {ylabel_html}
        <div class="chart-area">{''.join(cat_html)}</div>
    </div>
    <div class="legend">{legend}</div>"""

    html = _wrap_html(body, extra_style=style)
    _render_to_png(html, output)


# ============================================================
# TEMPLATE 7: concept_map
# ============================================================

def render_concept_map(data, output):
    center = data.get('center', '핵심')
    nodes = data['nodes']
    title = data.get('title', '개념 관계도')
    subtitle = data.get('subtitle', '')
    n = len(nodes)

    import math

    # Canvas and layout
    canvas_w, canvas_h = 1000, 900
    cx, cy = canvas_w // 2, canvas_h // 2
    radius = 340

    # SVG defs for gradient lines
    defs_svg = ['<defs>']
    for i in range(n):
        c1, _ = COLOR_PAIRS[i % len(COLOR_PAIRS)]
        defs_svg.append(f"""
        <linearGradient id="cg{i}" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="{P['primary']}" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="{c1}" stop-opacity="0.7"/>
        </linearGradient>""")
    defs_svg.append('</defs>')

    lines_svg = []
    outer_nodes = []
    center_icon = _detect_icon(center)

    for i, node in enumerate(nodes):
        angle = (2 * math.pi * i / n) - math.pi / 2
        nx = cx + radius * math.cos(angle)
        ny = cy + radius * math.sin(angle)
        c1, c2 = COLOR_PAIRS[i % len(COLOR_PAIRS)]
        node_icon = _detect_icon(node['name'])

        # Gradient line from center to node
        lines_svg.append(
            f'<line x1="{cx}" y1="{cy}" x2="{nx}" y2="{ny}" '
            f'stroke="url(#cg{i})" stroke-width="2.5" stroke-dasharray="8,4" />'
        )

        # Relation label at 60% position
        mx = cx + (nx - cx) * 0.60
        my = cy + (ny - cy) * 0.60
        rel_text = node.get('relation', '')
        tw = max(len(rel_text) * 9 + 24, 70)
        lines_svg.append(f"""
        <rect x="{mx - tw/2}" y="{my-14}" width="{tw}" height="28" rx="14"
              fill="white" stroke="{c1}" stroke-width="1.5" stroke-opacity="0.4"
              filter="url(#shadow)"/>
        <text x="{mx}" y="{my+5}" text-anchor="middle"
              font-family="'Noto Sans KR', sans-serif"
              font-size="13" font-weight="700" fill="{c1}">{rel_text}</text>
        """)

        # Small dot at connection point on center side
        dot_x = cx + (nx - cx) * 0.15
        dot_y = cy + (ny - cy) * 0.15
        lines_svg.append(f'<circle cx="{dot_x}" cy="{dot_y}" r="3" fill="{c1}" opacity="0.5"/>')

        # Outer node (HTML overlay with icon)
        outer_nodes.append(f"""
        <div class="cm-node" style="
            left: {nx - 85}px; top: {ny - 32}px;
            background: {_gradient(c1, c2)};
        "><i class="fa-solid {node_icon}"></i><span>{node['name']}</span></div>""")

    # Add shadow filter to SVG defs
    shadow_filter = """
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000" flood-opacity="0.08"/>
    </filter>"""
    defs_svg.insert(-1, shadow_filter)

    svg = f"""<svg width="{canvas_w}" height="{canvas_h}" style="position:absolute; top:0; left:0;">
        {''.join(defs_svg)}
        {''.join(lines_svg)}
    </svg>"""

    center_html = f"""<div class="cm-center" style="
        left: {cx - 90}px; top: {cy - 38}px;
        background: {_gradient(P['primary'], P['primary_light'])};
    "><i class="fa-solid {center_icon}" style="font-size:20px; opacity:0.9;"></i>
    <span>{center}</span></div>"""

    style = f"""
    .cm-container {{
        position: relative; width: {canvas_w}px; height: {canvas_h}px;
        margin: 0 auto;
    }}
    .cm-center {{
        position: absolute; width: 180px; height: 76px;
        border-radius: 20px; color: white;
        display: flex; align-items: center; justify-content: center; gap: 10px;
        font-size: 22px; font-weight: 900;
        box-shadow: 0 8px 32px rgba(27,58,92,0.3);
        z-index: 3;
    }}
    .cm-node {{
        position: absolute; width: 170px; height: 64px;
        border-radius: 50px; color: white;
        display: flex; align-items: center; justify-content: center; gap: 10px;
        font-size: 15px; font-weight: 700;
        box-shadow: 0 6px 20px rgba(0,0,0,0.15);
        z-index: 2; text-align: center;
    }}
    .cm-node i {{ font-size: 14px; opacity: 0.9; flex-shrink: 0; }}
    .cm-node span {{ white-space: nowrap; }}
    """

    sub_html = f'<p>{subtitle}</p>' if subtitle else ''
    body = f"""<div class="fig-title"><h1>{title}</h1>{sub_html}</div>
    <div class="cm-container">
        {svg}
        {center_html}
        {''.join(outer_nodes)}
    </div>"""

    html = _wrap_html(body, width=1200, extra_style=style, use_fa=True)
    _render_to_png(html, output, width=1200, wait_selector='.cm-node')


# ============================================================
# MERMAID.JS RENDERER — flowchart
# ============================================================

def _mermaid_html(diagram, title='', subtitle='', width=1800):
    """Generate HTML page with Mermaid diagram."""
    title_html = f'<h1>{title}</h1>' if title else ''
    sub_html = f'<p class="sub">{subtitle}</p>' if subtitle else ''
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#fff; font-family:'Noto Sans KR',sans-serif; padding:50px 70px; width:{width}px; }}
h1 {{ text-align:center; font-size:38px; font-weight:900; color:{P['title']}; }}
.sub {{ text-align:center; font-size:17px; color:#6B7B8D; font-style:italic; margin-top:8px; }}
.mermaid-wrap {{ display:flex; justify-content:center; margin-top:40px; }}
.mermaid svg {{ min-width:90% !important; height:auto !important; }}
.mermaid span.nodeLabel {{ font-size:18px !important; font-weight:700 !important; }}
.mermaid .edgeLabel {{ font-size:14px !important; }}
.mermaid .node rect, .mermaid .node polygon {{ rx:12 !important; ry:12 !important; }}
.mermaid .flowchart-link {{ stroke-width:2px !important; }}
</style></head><body>
{title_html}{sub_html}
<div class="mermaid-wrap"><pre class="mermaid">
{diagram}
</pre></div>
<script>
mermaid.initialize({{ startOnLoad:true, theme:'base',
  themeVariables: {{
    primaryColor:'{COLOR_PAIRS[0][0]}', primaryTextColor:'#fff',
    lineColor:'#CBD5E1', fontFamily:'"Noto Sans KR",sans-serif', fontSize:'16px'
  }},
  flowchart:{{ curve:'basis', padding:30, nodeSpacing:60, rankSpacing:100, htmlLabels:true, useMaxWidth:false }}
}});
</script></body></html>"""


def render_flowchart_mermaid(data, output):
    steps = data['steps']
    title = data.get('title', '프로세스 흐름도')
    subtitle = data.get('subtitle', '')

    lines = ['graph LR']

    # Per-node color classes
    for i, (c1, _) in enumerate(COLOR_PAIRS):
        lines.append(f'    classDef c{i} fill:{c1},color:#fff,stroke:none')

    # Nodes
    for i, step in enumerate(steps):
        lbl = step['label'].replace('"', "'")
        det = step.get('detail', '').replace('"', "'")
        text = f"{lbl}<br/>{det}" if det else lbl
        ci = i % len(COLOR_PAIRS)

        if step.get('type') == 'decision':
            lines.append(f'    s{i}{{"{text}"}}:::c{ci}')
        else:
            lines.append(f'    s{i}["{text}"]:::c{ci}')

    # Edges
    for i in range(len(steps) - 1):
        lines.append(f'    s{i} --> s{i+1}')

    diagram = '\n'.join(lines)
    w = max(1600, len(steps) * 300)
    html = _mermaid_html(diagram, title, subtitle, w)
    _render_to_png(html, output, w, wait_selector='.mermaid svg')


# ============================================================
# D3.JS RENDERER — bar_chart
# ============================================================

def render_bar_chart_d3(data, output):
    categories = data['categories']
    series_data = data['series']
    title = data.get('title', '')
    ylabel = data.get('ylabel', '')

    d3_data = json.dumps({'categories': categories, 'series': series_data})
    colors_json = json.dumps([cp[0] for cp in COLOR_PAIRS[:len(series_data)]])

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#fff; font-family:'Noto Sans KR',sans-serif; padding:50px 70px; width:1800px; }}
h1 {{ text-align:center; font-size:38px; font-weight:900; color:{P['title']}; margin-bottom:40px; }}
#chart {{ display:flex; justify-content:center; }}
</style></head><body>
<h1>{title}</h1>
<div id="chart"></div>
<script>
const data = {d3_data};
const colors = {colors_json};
const ylabel = '{ylabel}';
const margin = {{top:30, right:40, bottom:90, left:ylabel?80:50}};
const W = 1100 - margin.left - margin.right;
const H = 480 - margin.top - margin.bottom;

const svg = d3.select('#chart').append('svg')
  .attr('width', W+margin.left+margin.right)
  .attr('height', H+margin.top+margin.bottom)
  .append('g').attr('transform', `translate(${{margin.left}},${{margin.top}})`);

const x0 = d3.scaleBand().domain(data.categories).range([0,W]).padding(0.25);
const x1 = d3.scaleBand().domain(d3.range(data.series.length)).range([0,x0.bandwidth()]).padding(0.06);
const maxV = d3.max(data.series, s=>d3.max(s.values));
const y = d3.scaleLinear().domain([0, maxV*1.15]).range([H,0]);

// Horizontal grid
y.ticks(5).forEach(t => {{
  svg.append('line').attr('x1',0).attr('x2',W).attr('y1',y(t)).attr('y2',y(t))
    .attr('stroke','#EDF2F7').attr('stroke-width',1);
}});

// X axis
const xAx = svg.append('g').attr('transform',`translate(0,${{H}})`)
  .call(d3.axisBottom(x0).tickSize(0).tickPadding(14));
xAx.selectAll('text').style('font-size','16px').style('font-weight','500')
  .style('fill','#6B7B8D').style('font-family','"Noto Sans KR"');
xAx.select('.domain').attr('stroke','#EDF2F7');

// Y axis
const yAx = svg.append('g').call(d3.axisLeft(y).ticks(5).tickSize(0).tickPadding(10));
yAx.selectAll('text').style('font-size','14px').style('fill','#9BAEBF')
  .style('font-family','"Noto Sans KR"');
yAx.select('.domain').attr('stroke','#EDF2F7');

if (ylabel) {{
  svg.append('text').attr('transform','rotate(-90)').attr('y',-60).attr('x',-H/2)
    .attr('text-anchor','middle').style('font-size','15px').style('fill','#9BAEBF')
    .style('font-family','"Noto Sans KR"').text(ylabel);
}}

// Bars + labels
data.categories.forEach((cat,ci) => {{
  data.series.forEach((s,si) => {{
    svg.append('rect')
      .attr('x', x0(cat)+x1(si)).attr('y', y(s.values[ci]))
      .attr('width', x1.bandwidth()).attr('height', H-y(s.values[ci]))
      .attr('rx',5).attr('fill',colors[si]);
    svg.append('text')
      .attr('x', x0(cat)+x1(si)+x1.bandwidth()/2).attr('y', y(s.values[ci])-8)
      .attr('text-anchor','middle').style('font-size','15px').style('font-weight','700')
      .style('fill',colors[si]).style('font-family','"Noto Sans KR"')
      .text(s.values[ci]);
  }});
}});

// Legend
const lg = svg.append('g')
  .attr('transform',`translate(${{W/2 - data.series.length*75}}, ${{H+55}})`);
data.series.forEach((s,i) => {{
  const g = lg.append('g').attr('transform',`translate(${{i*150}},0)`);
  g.append('rect').attr('width',14).attr('height',14).attr('rx',3).attr('fill',colors[i]);
  g.append('text').attr('x',20).attr('y',12).style('font-size','15px').style('fill','#6B7B8D')
    .style('font-family','"Noto Sans KR"').text(s.name);
}});
</script></body></html>"""

    _render_to_png(html, output, wait_selector='#chart svg')


# ============================================================
# TEMPLATE 8: organization (추진체계도)
# ============================================================

def render_organization(data, output):
    """Research organization / team structure chart."""
    title = data.get('title', '연구 추진체계')
    lead = data.get('lead', {})
    teams = data.get('teams', [])

    lead_name = lead.get('name', '총괄책임자')
    lead_role = lead.get('role', '')
    lead_icon = lead.get('icon', _detect_icon(lead_name))

    team_blocks = []
    for i, team in enumerate(teams):
        c1, c2 = COLOR_PAIRS[i % len(COLOR_PAIRS)]
        t_icon = team.get('icon', _detect_icon(team['name']))
        members_html = ''
        if team.get('members'):
            items = ''.join(
                f'<div class="org-member"><i class="fas {_detect_icon(m) if isinstance(m, str) else _detect_icon(m.get("name",""))}"></i>'
                f'{m if isinstance(m, str) else m.get("name","")}</div>'
                for m in team['members']
            )
            members_html = f'<div class="org-members">{items}</div>'

        tasks_html = ''
        if team.get('tasks'):
            tasks_items = ''.join(f'<li>{t}</li>' for t in team['tasks'])
            tasks_html = f'<ul class="org-tasks">{tasks_items}</ul>'

        team_blocks.append(f"""
        <div class="org-team">
            <div class="org-team-header" style="background:{_gradient(c1, c2)};">
                <i class="fas {t_icon}"></i>
                <span>{team['name']}</span>
            </div>
            {members_html}
            {tasks_html}
        </div>""")

    n_cols = min(len(teams), 4) if teams else 1
    style = f"""
    .org-lead {{
        display: flex; align-items: center; justify-content: center; gap: 16px;
        background: {_gradient(P['primary'], P['primary_light'])};
        color: white; padding: 24px 48px; border-radius: 16px;
        font-size: 22px; font-weight: 800; margin: 0 auto 16px; width: fit-content;
        box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    }}
    .org-lead i {{ font-size: 28px; }}
    .org-lead-role {{ font-size: 15px; font-weight: 400; opacity: 0.85; margin-left: 8px; }}
    .org-connector {{ text-align: center; margin: 0 auto; }}
    .org-teams {{
        display: grid; grid-template-columns: repeat({n_cols}, 1fr);
        gap: 24px; margin-top: 16px;
    }}
    .org-team {{ border: 2px solid {P['border']}; border-radius: 14px; overflow: hidden; }}
    .org-team-header {{
        color: white; padding: 18px 20px; font-size: 18px; font-weight: 700;
        display: flex; align-items: center; gap: 10px;
    }}
    .org-team-header i {{ font-size: 20px; }}
    .org-members {{ padding: 14px 18px; display: flex; flex-wrap: wrap; gap: 8px; }}
    .org-member {{
        background: {P['row_alt']}; padding: 8px 14px; border-radius: 8px;
        font-size: 14px; color: {P['text_dark']}; display: flex; align-items: center; gap: 6px;
    }}
    .org-member i {{ color: {P['primary']}; font-size: 12px; }}
    .org-tasks {{
        padding: 8px 18px 16px 34px; font-size: 14px; color: {P['text_mid']};
        line-height: 1.8;
    }}
    """

    lead_role_html = f'<span class="org-lead-role">({lead_role})</span>' if lead_role else ''
    body = f"""<div class="fig-title"><h1>{title}</h1></div>
    <div class="org-lead"><i class="fas {lead_icon}"></i>{lead_name}{lead_role_html}</div>
    <div class="org-connector">{_ARROW_DOWN_SVG}</div>
    <div class="org-teams">{''.join(team_blocks)}</div>"""

    html = _wrap_html(body, extra_style=style, use_fa=True)
    _render_to_png(html, output)


# ============================================================
# TEMPLATE 9: kpi (기대효과/성과지표)
# ============================================================

def render_kpi(data, output):
    """KPI / expected outcomes dashboard."""
    title = data.get('title', '기대효과 및 성과지표')
    metrics = data.get('metrics', [])
    outcomes = data.get('outcomes', [])

    metric_cards = []
    for i, m in enumerate(metrics):
        c1, c2 = COLOR_PAIRS[i % len(COLOR_PAIRS)]
        icon = m.get('icon', _detect_icon(m.get('name', '')))
        metric_cards.append(f"""
        <div class="kpi-card">
            <div class="kpi-icon" style="background:{_gradient(c1, c2)};"><i class="fas {icon}"></i></div>
            <div class="kpi-value">{m.get('value', '')}<span class="kpi-unit">{m.get('unit', '')}</span></div>
            <div class="kpi-name">{m['name']}</div>
        </div>""")

    outcome_items = []
    for i, o in enumerate(outcomes):
        c1, _ = COLOR_PAIRS[i % len(COLOR_PAIRS)]
        name = o if isinstance(o, str) else o.get('name', '')
        desc = '' if isinstance(o, str) else o.get('desc', '')
        icon = _detect_icon(name)
        desc_html = f'<div class="outcome-desc">{desc}</div>' if desc else ''
        outcome_items.append(f"""
        <div class="outcome-item">
            <div class="outcome-icon" style="color:{c1};"><i class="fas {icon}"></i></div>
            <div class="outcome-text"><div class="outcome-name">{name}</div>{desc_html}</div>
        </div>""")

    n_metric_cols = min(len(metrics), 5) if metrics else 1
    style = f"""
    .kpi-grid {{ display: grid; grid-template-columns: repeat({n_metric_cols}, 1fr); gap: 24px; margin-bottom: 48px; }}
    .kpi-card {{ text-align: center; padding: 30px 20px; border: 2px solid {P['border']}; border-radius: 16px; }}
    .kpi-icon {{
        width: 60px; height: 60px; border-radius: 16px; margin: 0 auto 16px;
        display: flex; align-items: center; justify-content: center; color: white; font-size: 24px;
    }}
    .kpi-value {{ font-size: 36px; font-weight: 900; color: {P['title']}; }}
    .kpi-unit {{ font-size: 18px; font-weight: 500; color: {P['text_mid']}; margin-left: 4px; }}
    .kpi-name {{ font-size: 15px; color: {P['text_mid']}; margin-top: 6px; font-weight: 500; }}
    .outcomes-title {{
        font-size: 22px; font-weight: 800; color: {P['title']};
        margin-bottom: 24px; padding-bottom: 12px; border-bottom: 2px solid {P['border']};
    }}
    .outcomes-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; }}
    .outcome-item {{
        display: flex; align-items: flex-start; gap: 16px;
        padding: 20px; border-radius: 12px; background: {P['row_alt']};
    }}
    .outcome-icon {{ font-size: 24px; flex-shrink: 0; margin-top: 2px; }}
    .outcome-name {{ font-size: 16px; font-weight: 700; color: {P['text_dark']}; }}
    .outcome-desc {{ font-size: 14px; color: {P['text_mid']}; margin-top: 4px; line-height: 1.5; }}
    """

    outcomes_section = ''
    if outcome_items:
        outcomes_section = f"""
        <div class="outcomes-title">주요 기대효과</div>
        <div class="outcomes-grid">{''.join(outcome_items)}</div>"""

    body = f"""<div class="fig-title"><h1>{title}</h1></div>
    <div class="kpi-grid">{''.join(metric_cards)}</div>{outcomes_section}"""

    html = _wrap_html(body, extra_style=style, use_fa=True)
    _render_to_png(html, output)


# ============================================================
# TEMPLATE 10: roadmap (기술 로드맵)
# ============================================================

def render_roadmap(data, output):
    """Technology roadmap with phases and milestones."""
    title = data.get('title', '기술 로드맵')
    phases = data.get('phases', [])

    phase_blocks = []
    for i, phase in enumerate(phases):
        c1, c2 = COLOR_PAIRS[i % len(COLOR_PAIRS)]
        icon = phase.get('icon', _detect_icon(phase['name']))

        items_html = ''
        if phase.get('items'):
            items = ''.join(f'<div class="rm-item"><i class="fas fa-check"></i>{it}</div>' for it in phase['items'])
            items_html = f'<div class="rm-items">{items}</div>'

        milestone = phase.get('milestone', '')
        ms_html = f'<div class="rm-milestone"><i class="fas fa-flag"></i>{milestone}</div>' if milestone else ''

        phase_blocks.append(f"""
        <div class="rm-phase">
            <div class="rm-header" style="background:{_gradient(c1, c2)};">
                <i class="fas {icon}"></i>
                <div class="rm-phase-name">{phase['name']}</div>
                <div class="rm-period">{phase.get('period', '')}</div>
            </div>
            {items_html}{ms_html}
        </div>""")

    connected = []
    for i, block in enumerate(phase_blocks):
        connected.append(block)
        if i < len(phase_blocks) - 1:
            connected.append(f'<div class="rm-arrow">{_ARROW_SVG}</div>')

    style = f"""
    .rm-container {{ display: flex; align-items: flex-start; gap: 0; }}
    .rm-phase {{ flex: 1; border: 2px solid {P['border']}; border-radius: 14px; overflow: hidden; min-width: 0; }}
    .rm-header {{ color: white; padding: 24px 20px; text-align: center; }}
    .rm-header i {{ font-size: 28px; margin-bottom: 10px; display: block; }}
    .rm-phase-name {{ font-size: 18px; font-weight: 800; }}
    .rm-period {{ font-size: 13px; opacity: 0.85; margin-top: 4px; }}
    .rm-items {{ padding: 16px 18px; }}
    .rm-item {{
        display: flex; align-items: center; gap: 8px; padding: 8px 0;
        font-size: 14px; color: {P['text_dark']}; border-bottom: 1px solid {P['border']};
    }}
    .rm-item:last-child {{ border-bottom: none; }}
    .rm-item i {{ color: {P['primary']}; font-size: 12px; }}
    .rm-milestone {{
        padding: 12px 18px; background: {P['row_alt']};
        font-size: 14px; font-weight: 700; color: {P['accent']};
        display: flex; align-items: center; gap: 8px;
    }}
    .rm-arrow {{ display: flex; align-items: center; padding-top: 40px; flex-shrink: 0; }}
    """

    body = f"""<div class="fig-title"><h1>{title}</h1></div>
    <div class="rm-container">{''.join(connected)}</div>"""

    html = _wrap_html(body, extra_style=style, use_fa=True)
    _render_to_png(html, output)


# ============================================================
# TEMPLATE 11: manpower (인력투입 계획)
# ============================================================

def render_manpower(data, output):
    """Manpower allocation table with effort bars."""
    title = data.get('title', '인력투입 계획')
    members = data.get('members', [])
    total = data.get('total', 12)
    unit = data.get('unit', '월')

    rows = []
    for i, m in enumerate(members):
        c1, c2 = COLOR_PAIRS[i % len(COLOR_PAIRS)]
        cells = []
        effort = m.get('effort', [])
        for month in range(1, total + 1):
            val = effort[month - 1] if month <= len(effort) else 0
            if val > 0:
                opacity = min(0.4 + val * 0.3, 1.0)
                cells.append(f'<td class="mp-cell" style="background:{c1}; opacity:{opacity};">{val}</td>')
            else:
                cells.append('<td class="mp-cell mp-empty"></td>')
        total_effort = sum(effort) if effort else m.get('total', 0)
        rows.append(f"""
        <tr>
            <td class="mp-name" style="border-left: 4px solid {c1};">{m['name']}</td>
            <td class="mp-role">{m.get('role', '')}</td>
            {''.join(cells)}
            <td class="mp-total">{total_effort}</td>
        </tr>""")

    month_headers = ''.join(f'<th class="mp-month">{i}{unit}</th>' for i in range(1, total + 1))

    style = f"""
    .mp-table {{
        width: 100%; border-collapse: separate; border-spacing: 0;
        border: 2px solid {P['border']}; border-radius: 12px; overflow: hidden;
    }}
    .mp-table thead th {{
        background: {P['row_alt']}; padding: 14px 8px; font-size: 13px;
        font-weight: 700; color: {P['text_mid']}; text-align: center;
        border-bottom: 2px solid {P['border']};
    }}
    .mp-name {{ padding: 12px 16px; font-weight: 700; font-size: 15px; color: {P['text_dark']}; white-space: nowrap; }}
    .mp-role {{ padding: 12px 12px; font-size: 13px; color: {P['text_mid']}; white-space: nowrap; }}
    .mp-cell {{ text-align: center; padding: 10px 4px; font-size: 13px; font-weight: 700; color: white; min-width: 40px; }}
    .mp-empty {{ background: transparent; }}
    .mp-total {{ text-align: center; padding: 12px 8px; font-size: 15px; font-weight: 900; color: {P['accent']}; }}
    .mp-month {{ min-width: 40px; }}
    tbody tr {{ border-bottom: 1px solid {P['border']}; }}
    """

    body = f"""<div class="fig-title"><h1>{title}</h1></div>
    <table class="mp-table">
        <thead><tr>
            <th style="text-align:left; padding-left:20px;">성명</th><th>역할</th>
            {month_headers}<th>계</th>
        </tr></thead>
        <tbody>{''.join(rows)}</tbody>
    </table>"""

    w = max(1600, total * 80 + 400)
    html = _wrap_html(body, width=w, extra_style=style)
    _render_to_png(html, output, width=w)


# ============================================================
# TEMPLATE 12: budget (예산 편성)
# ============================================================

def render_budget(data, output):
    """Budget allocation chart with donut and breakdown table."""
    title = data.get('title', '연구비 편성')
    categories = data.get('categories', [])
    total_amount = data.get('total', sum(c.get('amount', 0) for c in categories))

    segments = []
    offset = 0
    circumference = 3.14159 * 2 * 45
    for i, cat in enumerate(categories):
        c1, _ = COLOR_PAIRS[i % len(COLOR_PAIRS)]
        pct = (cat['amount'] / total_amount * 100) if total_amount else 0
        dash = pct * circumference / 100
        segments.append(
            f'<circle cx="60" cy="60" r="45" fill="none" stroke="{c1}" '
            f'stroke-width="20" stroke-dasharray="{dash} {circumference}" '
            f'stroke-dashoffset="{-offset}" />'
        )
        offset += dash

    table_rows = []
    for i, cat in enumerate(categories):
        c1, _ = COLOR_PAIRS[i % len(COLOR_PAIRS)]
        pct = (cat['amount'] / total_amount * 100) if total_amount else 0
        amount_str = f"{cat['amount']:,}" if isinstance(cat['amount'], int) else str(cat['amount'])
        details = cat.get('details', '')
        details_html = f'<div class="budget-details">{details}</div>' if details else ''
        table_rows.append(f"""
        <tr>
            <td><div class="budget-dot" style="background:{c1};"></div></td>
            <td class="budget-cat-name">{cat['name']}</td>
            <td class="budget-amount">{amount_str}</td>
            <td class="budget-pct">{pct:.1f}%</td>
            <td class="budget-detail-cell">{details_html}</td>
        </tr>""")

    total_str = f"{total_amount:,}" if isinstance(total_amount, int) else str(total_amount)
    unit_label = data.get('unit', '천원')

    style = f"""
    .budget-layout {{ display: grid; grid-template-columns: 280px 1fr; gap: 48px; align-items: center; }}
    .budget-donut {{ position: relative; width: 240px; height: 240px; margin: 0 auto; }}
    .budget-donut svg {{ width: 100%; height: 100%; transform: rotate(-90deg); }}
    .budget-center {{
        position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center;
    }}
    .budget-center-label {{ font-size: 13px; color: {P['text_mid']}; }}
    .budget-center-value {{ font-size: 24px; font-weight: 900; color: {P['title']}; }}
    .budget-center-unit {{ font-size: 14px; color: {P['text_mid']}; }}
    .budget-table {{ width: 100%; border-collapse: collapse; }}
    .budget-table th {{
        text-align: left; padding: 12px 8px; font-size: 13px;
        font-weight: 700; color: {P['text_mid']}; border-bottom: 2px solid {P['border']};
    }}
    .budget-table td {{ padding: 14px 8px; border-bottom: 1px solid {P['border']}; }}
    .budget-dot {{ width: 14px; height: 14px; border-radius: 4px; }}
    .budget-cat-name {{ font-size: 16px; font-weight: 700; color: {P['text_dark']}; }}
    .budget-amount {{ font-size: 16px; font-weight: 800; color: {P['title']}; text-align: right; }}
    .budget-pct {{ font-size: 14px; color: {P['text_mid']}; text-align: center; }}
    .budget-detail-cell {{ font-size: 13px; color: {P['text_mid']}; }}
    .budget-total {{ font-weight: 900; font-size: 18px; color: {P['accent']}; text-align: right; padding: 16px 8px; }}
    """

    body = f"""<div class="fig-title"><h1>{title}</h1></div>
    <div class="budget-layout">
        <div class="budget-donut">
            <svg viewBox="0 0 120 120">{''.join(segments)}</svg>
            <div class="budget-center">
                <div class="budget-center-label">총 연구비</div>
                <div class="budget-center-value">{total_str}</div>
                <div class="budget-center-unit">{unit_label}</div>
            </div>
        </div>
        <table class="budget-table">
            <thead><tr><th></th><th>항목</th><th style="text-align:right;">금액 ({unit_label})</th><th style="text-align:center;">비율</th><th>세부내역</th></tr></thead>
            <tbody>{''.join(table_rows)}
            <tr><td></td><td style="font-weight:900;">합계</td><td class="budget-total">{total_str}</td><td></td><td></td></tr>
            </tbody>
        </table>
    </div>"""

    html = _wrap_html(body, extra_style=style)
    _render_to_png(html, output)


# ============================================================
# TEMPLATE 13: overview (연구 개요도)
# ============================================================

def render_overview(data, output):
    """Research overview with goal, methods, and outcomes."""
    title = data.get('title', '연구 개요')
    goal = data.get('goal', '')
    methods = data.get('methods', [])
    outcomes = data.get('outcomes', [])
    keywords = data.get('keywords', [])

    method_cards = []
    for i, m in enumerate(methods):
        c1, c2 = COLOR_PAIRS[i % len(COLOR_PAIRS)]
        name = m if isinstance(m, str) else m.get('name', '')
        desc = '' if isinstance(m, str) else m.get('desc', '')
        icon = _detect_icon(name)
        desc_html = f'<div class="ov-method-desc">{desc}</div>' if desc else ''
        method_cards.append(f"""
        <div class="ov-method" style="border-top: 4px solid {c1};">
            <div class="ov-method-icon" style="color:{c1};"><i class="fas {icon}"></i></div>
            <div class="ov-method-name">{name}</div>{desc_html}
        </div>""")

    outcome_items = []
    for i, o in enumerate(outcomes):
        c1, _ = COLOR_PAIRS[i % len(COLOR_PAIRS)]
        name = o if isinstance(o, str) else o.get('name', '')
        outcome_items.append(
            f'<div class="ov-outcome"><i class="fas fa-check-circle" style="color:{c1};"></i>{name}</div>'
        )

    kw_html = ''
    if keywords:
        badges = ''.join(f'<span class="ov-kw">{k}</span>' for k in keywords)
        kw_html = f'<div class="ov-keywords">{badges}</div>'

    n_method_cols = min(len(methods), 4) if methods else 1
    style = f"""
    .ov-goal {{
        background: {_gradient(P['primary'], P['primary_light'])};
        color: white; padding: 28px 36px; border-radius: 16px;
        font-size: 20px; font-weight: 700; line-height: 1.5;
        text-align: center; margin-bottom: 40px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.12);
    }}
    .ov-goal-label {{ font-size: 14px; font-weight: 500; opacity: 0.8; margin-bottom: 8px; }}
    .ov-section-title {{
        font-size: 20px; font-weight: 800; color: {P['title']};
        margin-bottom: 20px; padding-left: 14px; border-left: 4px solid {P['accent']};
    }}
    .ov-methods {{ display: grid; grid-template-columns: repeat({n_method_cols}, 1fr); gap: 20px; margin-bottom: 40px; }}
    .ov-method {{ padding: 24px 20px; border-radius: 12px; background: white; border: 1px solid {P['border']}; }}
    .ov-method-icon {{ font-size: 28px; margin-bottom: 12px; }}
    .ov-method-name {{ font-size: 16px; font-weight: 700; color: {P['text_dark']}; }}
    .ov-method-desc {{ font-size: 13px; color: {P['text_mid']}; margin-top: 6px; line-height: 1.5; }}
    .ov-outcomes {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-bottom: 32px; }}
    .ov-outcome {{
        display: flex; align-items: center; gap: 10px;
        padding: 16px 20px; border-radius: 10px; background: {P['row_alt']};
        font-size: 15px; font-weight: 600; color: {P['text_dark']};
    }}
    .ov-outcome i {{ font-size: 18px; flex-shrink: 0; }}
    .ov-keywords {{ display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; margin-top: 20px; }}
    .ov-kw {{ background: {P['primary']}22; color: {P['primary']}; padding: 8px 18px; border-radius: 50px; font-size: 14px; font-weight: 700; }}
    """

    connector = f'<div style="text-align:center; margin: 8px 0;">{_ARROW_DOWN_SVG}</div>'
    body = f"""<div class="fig-title"><h1>{title}</h1></div>
    <div class="ov-goal"><div class="ov-goal-label">연구 목표</div>{goal}</div>
    {connector}
    <div class="ov-section-title">연구 방법</div>
    <div class="ov-methods">{''.join(method_cards)}</div>
    {connector}
    <div class="ov-section-title">기대 성과</div>
    <div class="ov-outcomes">{''.join(outcome_items)}</div>
    {kw_html}"""

    html = _wrap_html(body, extra_style=style, use_fa=True)
    _render_to_png(html, output)


# ============================================================
# TEMPLATE 14: dataflow (데이터 흐름도)
# ============================================================

def render_dataflow(data, output):
    """Data flow diagram with layers and connections."""
    title = data.get('title', '데이터 흐름도')
    layers = data.get('layers', [])

    layer_blocks = []
    for i, layer in enumerate(layers):
        c1, c2 = COLOR_PAIRS[i % len(COLOR_PAIRS)]
        layer_icon = layer.get('icon', _detect_icon(layer['name']))

        nodes_html = ''
        if layer.get('nodes'):
            items = []
            for n in layer['nodes']:
                n_name = n if isinstance(n, str) else n.get('name', '')
                n_icon = _detect_icon(n_name)
                items.append(f'<div class="df-node"><i class="fas {n_icon}"></i>{n_name}</div>')
            nodes_html = f'<div class="df-nodes">{"".join(items)}</div>'

        layer_blocks.append(f"""
        <div class="df-layer">
            <div class="df-layer-label" style="background:{_gradient(c1, c2)};">
                <i class="fas {layer_icon}"></i>{layer['name']}
            </div>
            {nodes_html}
        </div>""")

    connected = []
    for i, block in enumerate(layer_blocks):
        connected.append(block)
        if i < len(layer_blocks) - 1:
            connected.append(f'<div class="df-arrow">{_ARROW_DOWN_SVG}</div>')

    style = f"""
    .df-container {{ display: flex; flex-direction: column; align-items: center; gap: 0; }}
    .df-layer {{ width: 90%; border: 2px solid {P['border']}; border-radius: 14px; overflow: hidden; }}
    .df-layer-label {{
        color: white; padding: 16px 24px; font-size: 18px; font-weight: 800;
        display: flex; align-items: center; gap: 12px;
    }}
    .df-layer-label i {{ font-size: 22px; }}
    .df-nodes {{ display: flex; flex-wrap: wrap; gap: 12px; padding: 18px 24px; }}
    .df-node {{
        display: flex; align-items: center; gap: 8px;
        padding: 12px 18px; border-radius: 10px;
        background: {P['row_alt']}; font-size: 14px; font-weight: 600; color: {P['text_dark']};
    }}
    .df-node i {{ color: {P['primary']}; font-size: 16px; }}
    .df-arrow {{ text-align: center; flex-shrink: 0; }}
    """

    body = f"""<div class="fig-title"><h1>{title}</h1></div>
    <div class="df-container">{''.join(connected)}</div>"""

    html = _wrap_html(body, extra_style=style, use_fa=True)
    _render_to_png(html, output)


# ============================================================
# Template Registry
# ============================================================

# HTML-only renderers (fallback)
TEMPLATES_HTML = {
    'flowchart':        render_flowchart,
    'architecture':     render_architecture,
    'comparison_table': render_comparison_table,
    'timeline':         render_timeline,
    'hierarchy':        render_hierarchy,
    'bar_chart':        render_bar_chart,
    'concept_map':      render_concept_map,
    'organization':     render_organization,
    'kpi':              render_kpi,
    'roadmap':          render_roadmap,
    'manpower':         render_manpower,
    'budget':           render_budget,
    'overview':         render_overview,
    'dataflow':         render_dataflow,
}

# Auto: best renderer per template (Mermaid/D3/HTML)
TEMPLATES = {
    'flowchart':        render_flowchart_mermaid,   # Mermaid
    'architecture':     render_architecture,         # HTML
    'comparison_table': render_comparison_table,     # HTML
    'timeline':         render_timeline,             # HTML
    'hierarchy':        render_hierarchy,             # HTML
    'bar_chart':        render_bar_chart_d3,         # D3
    'concept_map':      render_concept_map,          # HTML
    'organization':     render_organization,         # HTML
    'kpi':              render_kpi,                  # HTML
    'roadmap':          render_roadmap,              # HTML
    'manpower':         render_manpower,             # HTML
    'budget':           render_budget,               # HTML
    'overview':         render_overview,             # HTML
    'dataflow':         render_dataflow,             # HTML
}

ALIASES = {
    '흐름도': 'flowchart', '프로세스': 'flowchart',
    '구조도': 'architecture', '시스템': 'architecture', '아키텍처': 'architecture',
    '비교표': 'comparison_table', '비교': 'comparison_table',
    '타임라인': 'timeline', '일정': 'timeline', '간트': 'timeline', '추진일정': 'timeline',
    '계층': 'hierarchy', '분류': 'hierarchy',
    '막대': 'bar_chart', '차트': 'bar_chart', '그래프': 'bar_chart',
    '개념도': 'concept_map', '관계도': 'concept_map', '마인드맵': 'concept_map',
    # 새 템플릿 aliases
    '추진체계': 'organization', '조직도': 'organization', '연구팀': 'organization',
    '기대효과': 'kpi', '성과지표': 'kpi', 'KPI': 'kpi',
    '로드맵': 'roadmap', '기술로드맵': 'roadmap',
    '인력': 'manpower', '인력투입': 'manpower', '참여인력': 'manpower',
    '예산': 'budget', '연구비': 'budget', '예산편성': 'budget',
    '개요': 'overview', '연구개요': 'overview', '총괄개요': 'overview',
    '데이터흐름': 'dataflow', '데이터': 'dataflow',
}


def resolve_type(raw_type):
    t = raw_type.strip().lower()
    if t in TEMPLATES:
        return t
    if t in ALIASES:
        return ALIASES[t]
    return None


def render(fig_type, data, output, theme=None, backend='auto'):
    """Render a figure.

    backend: 'auto' | 'html' | 'mpl' | 'gemini' | 'copilot'
      - auto/html: HTML/CSS/Mermaid/D3 rendering (local, fast)
      - gemini: AI image via Gemini NanoBanana + text overlay
      - copilot: AI image via Copilot Designer + text overlay
    """
    if theme:
        set_theme(theme)

    # AI image generation backends
    if backend in ('gemini', 'copilot', 'chatgpt'):
        return _render_ai_image(fig_type, data, output, platform=backend)

    resolved = resolve_type(fig_type)
    if resolved is None:
        return False
    registry = TEMPLATES if backend == 'auto' else TEMPLATES_HTML
    registry[resolved](data, output)
    return True


def _render_ai_image(fig_type, data, output, platform='gemini'):
    """Generate figure using AI image generation (Gemini/Copilot).

    data dict should contain:
      - prompt: (optional) Direct English prompt for image generation
      - description: (optional) Korean description → auto-converted to prompt
      - title: Korean title for text overlay
      - subtitle: (optional) Korean subtitle for overlay
      - items: (optional) List of badge labels for overlay
      - style: (optional) 'infographic'|'diagram'|'concept'|'process'
    """
    from ai_image import build_prompt, apply_overlay

    # Build prompt for user/Claude to send via MCP
    prompt = data.get('prompt', '')
    if not prompt:
        desc = data.get('description', data.get('title', ''))
        style = data.get('style', 'infographic')
        prompt = build_prompt(desc, style, platform)

    # If raw image already exists (downloaded via MCP), apply overlay
    raw_path = data.get('raw_image')
    if raw_path and os.path.exists(raw_path):
        title = data.get('title')
        subtitle = data.get('subtitle')
        items = data.get('items')
        if title or subtitle or items:
            apply_overlay(raw_path, output, title, subtitle, items)
        else:
            import shutil
            shutil.copy2(raw_path, output)
        return True

    # Otherwise, print the prompt for MCP workflow
    print(f"[AI Image] Platform: {platform}")
    print(f"[AI Image] Prompt:\n{prompt}")
    print(f"[AI Image] → Use Chrome MCP to generate, then set data['raw_image'] and re-run")
    return False


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Figure Engine v2 (Mermaid+D3+HTML)')
    parser.add_argument('--type', help='Template type')
    parser.add_argument('--data', help='JSON data file')
    parser.add_argument('--output', help='Output PNG path')
    parser.add_argument('--backend', default='auto',
                        choices=['auto', 'html', 'mpl', 'gemini', 'copilot', 'chatgpt'],
                        help='auto=Mermaid+D3+HTML, html=HTML only, mpl=matplotlib, gemini/copilot/chatgpt=AI image')
    parser.add_argument('--theme', default='nature', choices=list(THEMES.keys()),
                        help='Color theme (default: nature)')
    parser.add_argument('--list', action='store_true', help='List templates')
    parser.add_argument('--themes', action='store_true', help='List available themes')
    args = parser.parse_args()

    if args.themes:
        for k, v in THEMES.items():
            colors_preview = ' '.join(c[0] for c in v['colors'][:5])
            print(f"  {k:8s}  {v['name']:20s}  {colors_preview}")
        return

    if args.list:
        print("Templates:", ', '.join(sorted(TEMPLATES.keys())))
        print("Aliases:", ', '.join(f'{k}->{v}' for k, v in sorted(ALIASES.items())))
        return

    set_theme(args.theme)

    if args.backend == 'mpl':
        from figure_engine_mpl import render as mpl_render
        with open(args.data, 'r', encoding='utf-8') as f:
            data = json.load(f)
        ok = mpl_render(args.type, data, args.output)
        if ok:
            print(f"Generated (mpl/{args.type}): {args.output}")
        else:
            print(f"ERROR: Unknown type '{args.type}'")
            sys.exit(1)
        return

    if not args.type or not args.data or not args.output:
        parser.print_help()
        sys.exit(1)

    with open(args.data, 'r', encoding='utf-8') as f:
        data = json.load(f)

    ok = render(args.type, data, args.output, backend=args.backend)
    if ok:
        print(f"Generated ({args.backend}/{args.type}): {args.output}")
    else:
        print(f"ERROR: Unknown type '{args.type}'")
        sys.exit(1)


if __name__ == '__main__':
    main()
