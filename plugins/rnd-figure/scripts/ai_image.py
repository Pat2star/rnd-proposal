"""
AI Image Generator — 멀티 플랫폼 지원 (Gemini / Copilot / ChatGPT)
Chrome MCP 브라우저 자동화로 무료 AI 이미지 생성 + 한국어 텍스트 오버레이.

=== 사용 모드 ===

1. 프롬프트 모드: 사용자 아이디어 → 정교한 프롬프트 → 이미지 생성
2. 계획서 모드: 연구계획서 MD → 섹션별 그림 자동 생성 (추후)

=== 지원 플랫폼 ===

| 플랫폼  | 모델          | 무료 한도     | 로그인       |
|---------|--------------|-------------|-------------|
| gemini  | NanoBanana   | 무제한       | Google 계정  |
| copilot | DALL-E 3     | 15크레딧/월  | MS 계정      |
| chatgpt | DALL-E / GPT | 제한적       | OpenAI 계정  |

=== MCP 워크플로우 (Claude Code 내에서) ===

Claude Code가 직접 Chrome MCP 도구를 사용하여:
1. 플랫폼 웹사이트에 접속 (이미 로그인된 상태)
2. 프롬프트 입력 + 전송
3. 생성된 이미지 다운로드
4. 텍스트 오버레이 합성

이 파일의 함수들은 MCP 워크플로우의 각 단계를 지원합니다.
"""

import os
import base64

# ============================================================
# Platform Configuration
# ============================================================

PLATFORMS = {
    'gemini': {
        'name': 'Google Gemini (NanoBanana)',
        'url': 'https://gemini.google.com/app',
        'model': 'Imagen 3 / NanoBanana',
        'free_limit': 'unlimited',
        'text_in_image': False,  # doesn't add unwanted text
        'korean_text_quality': 'moderate',  # Korean text OK with good prompts
        'best_for': 'clean backgrounds, text overlay friendly',
    },
    'copilot': {
        'name': 'Microsoft Copilot (Designer)',
        'url': 'https://copilot.microsoft.com',
        'model': 'DALL-E 3',
        'free_limit': '15 credits/month',
        'text_in_image': True,  # tends to add text
        'korean_text_quality': 'poor',  # English OK, Korean unreliable
        'best_for': 'high detail, dramatic lighting',
    },
    'chatgpt': {
        'name': 'ChatGPT (GPT-4o)',
        'url': 'https://chatgpt.com',
        'model': 'GPT-4o / GPT Image',
        'free_limit': '2 images/day (free tier)',
        'text_in_image': True,
        'korean_text_quality': 'good',  # GPT-4o handles Korean text well
        'best_for': 'artistic styles, text-in-image, creative compositions',
    },
}

# Overlay modes
OVERLAY_AI = 'ai'            # AI generates text directly in image
OVERLAY_PLAYWRIGHT = 'playwright'  # Playwright HTML/CSS overlay (reliable)
OVERLAY_AUTO = 'auto'        # Auto-select based on platform capability


def list_platforms():
    """Print available platforms."""
    for key, info in PLATFORMS.items():
        print(f"  {key:10s}  {info['name']:35s}  (free: {info['free_limit']})")


# ============================================================
# Prompt Engineering
# ============================================================

# Style presets for research proposal figures
STYLE_PRESETS = {
    'infographic': {
        'desc': 'professional infographic-style 3D illustration, '
                'clean modern design, tech corporate aesthetic, '
                'blue gradient background with subtle grid pattern',
        'use_for': 'system overview, architecture diagrams',
    },
    'diagram': {
        'desc': 'clean technical diagram illustration, '
                'flat design with isometric elements, '
                'white background with subtle shadows',
        'use_for': 'methodology, workflow explanations',
    },
    'concept': {
        'desc': 'conceptual illustration with metaphorical scene, '
                '3D rendered characters and objects, '
                'warm professional lighting, modern tech setting',
        'use_for': 'abstract concepts, analogies',
    },
    'process': {
        'desc': 'process flow illustration with connected stages, '
                'futuristic conveyor belt or pipeline metaphor, '
                'clean 3D rendered style, professional colors',
        'use_for': 'step-by-step processes, pipelines',
    },
    'comparison': {
        'desc': 'split-screen comparison illustration, '
                'before/after or side-by-side layout, '
                '3D rendered with clear visual contrast',
        'use_for': 'before/after, existing vs proposed',
    },
    'data': {
        'desc': 'data visualization themed illustration, '
                'holographic charts and dashboards floating in space, '
                'dark blue background with glowing data elements',
        'use_for': 'results, analysis, performance',
    },
    'organization': {
        'desc': 'organizational hierarchy illustration, '
                '3D rendered team structure with connected nodes, '
                'professional corporate setting with clean lines',
        'use_for': 'team structure, research organization',
    },
    'roadmap': {
        'desc': 'technology roadmap illustration with milestone markers, '
                'futuristic pathway with glowing checkpoints, '
                'timeline stretching into the horizon',
        'use_for': 'technology roadmap, development phases',
    },
    'overview': {
        'desc': 'research overview illustration showing connected elements, '
                'central hub with radiating components, '
                'clean modern design with layered depth',
        'use_for': 'research overview, project summary',
    },
    'budget': {
        'desc': 'financial allocation illustration with proportional elements, '
                'clean pie/donut visualization with labeled segments, '
                'professional business aesthetic',
        'use_for': 'budget allocation, resource distribution',
    },
}


def build_prompt(description, style='infographic', platform='gemini',
                 overlay=None, overlay_mode=OVERLAY_AUTO):
    """Build an optimized English image prompt from a Korean description.

    Args:
        description: What the image should depict (Korean or English)
        style: Style preset key or custom style description
        platform: Target platform (affects prompt tuning)
        overlay: dict with keys: title, subtitle, items (Korean text to embed)
        overlay_mode: 'ai' (AI renders text), 'playwright' (post-process), 'auto'

    Returns:
        Optimized English prompt string
    """
    if style in STYLE_PRESETS:
        style_desc = STYLE_PRESETS[style]['desc']
    else:
        style_desc = style

    # Determine effective overlay mode
    effective_mode = _resolve_overlay_mode(platform, overlay_mode)

    if effective_mode == OVERLAY_AI and overlay:
        # AI generates text directly in the image
        prompt = _build_prompt_with_text(description, style_desc, overlay)
    else:
        # No text in image (will be overlaid later, or no overlay)
        prompt = (
            f"Generate a wide 16:9 {style_desc}. "
            f"The scene depicts: {description}. "
            f"Leave empty space at top-left corner for text overlay. "
            f"Professional and visually impressive, "
            f"suitable for a research proposal presentation."
        )
        if PLATFORMS.get(platform, {}).get('text_in_image', False):
            prompt += " IMPORTANT: Do NOT include any text, words, or letters in the image."

    return prompt


def _resolve_overlay_mode(platform, mode):
    """Determine effective overlay mode based on platform capability."""
    if mode != OVERLAY_AUTO:
        return mode
    quality = PLATFORMS.get(platform, {}).get('korean_text_quality', 'poor')
    return OVERLAY_AI if quality in ('good', 'moderate') else OVERLAY_PLAYWRIGHT


def _build_prompt_with_text(description, style_desc, overlay):
    """Build prompt that instructs AI to render Korean text naturally in the image.

    The text should look like part of the design, not a post-processed overlay.
    """
    title = overlay.get('title', '')
    subtitle = overlay.get('subtitle', '')
    items = overlay.get('items', [])

    prompt = (
        f"Generate a wide 16:9 {style_desc}. "
        f"The scene depicts: {description}. "
        f"This is a professional presentation slide image for a research proposal. "
    )

    # Text layout instructions
    text_instructions = []
    if title:
        text_instructions.append(
            f"Display the title text \"{title}\" prominently in the upper-left area "
            f"using a bold, clean sans-serif font. The title should be large and clearly readable."
        )
    if subtitle:
        text_instructions.append(
            f"Below the title, display subtitle text \"{subtitle}\" in a smaller, "
            f"lighter weight font."
        )
    if items:
        items_str = ', '.join(f'"{item}"' for item in items)
        text_instructions.append(
            f"At the bottom-left area, display keyword badges or tags: {items_str}. "
            f"Each keyword should be in a rounded pill-shaped badge with semi-transparent background."
        )

    if text_instructions:
        prompt += (
            "IMPORTANT TEXT RENDERING INSTRUCTIONS: "
            + " ".join(text_instructions)
            + " The text must be in Korean (한국어). "
            "Render all Korean characters accurately and clearly — "
            "every character must be correct and legible. "
            "The text should look like a natural part of the design, "
            "integrated with the background using subtle shadow, gradient overlay, "
            "or frosted panel behind the text area. "
            "Do NOT just place plain white text on top — "
            "make it look like a professionally designed infographic or presentation slide. "
        )

    prompt += "Professional, visually impressive, suitable for a government research proposal."
    return prompt


def refine_prompt(user_idea, style='infographic', platform='gemini',
                  overlay=None, overlay_mode=OVERLAY_AUTO):
    """Refine a rough user idea into a polished prompt.

    Args:
        user_idea: User's rough description (Korean)
        style: Style preset
        platform: Target platform
        overlay: dict with title/subtitle/items for text embedding
        overlay_mode: 'ai', 'playwright', or 'auto'

    Returns:
        dict with 'prompt', 'overlay_mode', and 'suggestions'
    """
    effective_mode = _resolve_overlay_mode(platform, overlay_mode)
    base = build_prompt(user_idea, style, platform, overlay, overlay_mode)

    return {
        'prompt': base,
        'user_idea': user_idea,
        'style': style,
        'platform': platform,
        'overlay': overlay,
        'overlay_mode': effective_mode,
        'needs_playwright_overlay': effective_mode == OVERLAY_PLAYWRIGHT and overlay is not None,
        'refinement_tips': [
            'Add specific visual elements (e.g., "holographic screens", "robot arms")',
            'Specify color scheme (e.g., "blue and white", "warm orange tones")',
            'Mention composition (e.g., "centered layout", "perspective from above")',
            'Add mood (e.g., "futuristic", "clean", "energetic")',
        ],
    }


def proposal_to_prompts(sections_dir):
    """Read research proposal sections and generate figure prompts.

    Args:
        sections_dir: Path to outputs/sections/ directory

    Returns:
        List of dicts with figure specs: {section, placeholder, prompt, style, overlay}
    """
    import re

    figures = []
    if not os.path.isdir(sections_dir):
        return figures

    for fname in sorted(os.listdir(sections_dir)):
        if not fname.endswith('.md'):
            continue
        fpath = os.path.join(sections_dir, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find [FIG-N: description] placeholders
        for match in re.finditer(r'\[FIG-(\d+):\s*(.+?)\]', content):
            fig_num = int(match.group(1))
            fig_desc = match.group(2).strip()

            # Auto-detect style from description
            style = _detect_style(fig_desc)

            figures.append({
                'section': fname,
                'placeholder': match.group(0),
                'fig_num': fig_num,
                'description': fig_desc,
                'style': style,
                'prompt': build_prompt(fig_desc, style),
                'output_name': f'fig{fig_num:02d}_{_slugify(fig_desc)}.png',
                'overlay': {
                    'title': fig_desc,
                },
            })

    return figures


def _detect_style(desc):
    """Auto-detect appropriate style from Korean description."""
    keywords = {
        'infographic': ['시스템', '구조', '개요', '아키텍처', '프레임워크'],
        'process': ['프로세스', '파이프라인', '흐름', '단계', '절차', '워크플로'],
        'concept': ['개념', '비유', '은유', '원리', '메타포'],
        'comparison': ['비교', '대비', '기존', 'vs', '차이'],
        'data': ['결과', '성능', '분석', '데이터', '평가', '실험'],
        'diagram': ['방법론', '모델', '알고리즘', '설계'],
    }
    desc_lower = desc.lower()
    for style, kws in keywords.items():
        if any(kw in desc_lower for kw in kws):
            return style
    return 'infographic'


def _slugify(text):
    """Convert Korean text to filename-safe slug."""
    import re
    text = re.sub(r'[^\w\s가-힣]', '', text)
    text = re.sub(r'\s+', '_', text.strip())
    return text[:30]


# ============================================================
# Text Overlay Compositing
# ============================================================

def apply_overlay(input_path, output_path, title=None, subtitle=None,
                  items=None, width=None, height=None):
    """Apply Korean text overlay on an AI-generated image.

    Args:
        input_path: Path to the raw AI-generated image
        output_path: Path to save the composited image
        title: Main title text (supports \\n for line breaks)
        subtitle: Subtitle text (supports \\n)
        items: List of badge label strings
        width/height: Override dimensions (auto-detected from image if None)
    """
    from playwright.sync_api import sync_playwright
    from PIL import Image

    # Auto-detect dimensions
    if width is None or height is None:
        with Image.open(input_path) as img:
            width, height = img.size

    with open(input_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode()

    items_html = ''
    if items:
        badges = ''.join(f'<span class="badge">{item}</span>' for item in items)
        items_html = f'<div class="items">{badges}</div>'

    title_html = f'<div class="title">{title}</div>' if title else ''
    sub_html = f'<div class="subtitle">{subtitle}</div>' if subtitle else ''

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: {width}px; height: {height}px;
    position: relative; overflow: hidden;
    font-family: 'Noto Sans KR', sans-serif;
}}
.bg {{ width: 100%; height: 100%; object-fit: cover; }}
.overlay {{
    position: absolute; top: 0; left: 0; width: 55%; height: 100%;
    background: linear-gradient(135deg,
        rgba(0,0,0,0.72) 0%, rgba(0,0,0,0.30) 60%, transparent 100%);
    padding: {int(height*0.07)}px {int(width*0.035)}px;
    display: flex; flex-direction: column; justify-content: center;
}}
.title {{
    color: white; font-size: {max(24, int(height*0.055))}px; font-weight: 900;
    line-height: 1.35; margin-bottom: {int(height*0.02)}px;
    text-shadow: 0 2px 8px rgba(0,0,0,0.4);
    white-space: pre-line;
}}
.subtitle {{
    color: rgba(255,255,255,0.88);
    font-size: {max(14, int(height*0.028))}px; font-weight: 400;
    line-height: 1.6; margin-bottom: {int(height*0.03)}px;
    text-shadow: 0 1px 4px rgba(0,0,0,0.3);
    white-space: pre-line;
}}
.items {{ display: flex; flex-wrap: wrap; gap: 10px; }}
.badge {{
    background: rgba(255,255,255,0.2);
    border: 1px solid rgba(255,255,255,0.3);
    color: white; font-size: {max(12, int(height*0.024))}px; font-weight: 700;
    padding: 8px 18px; border-radius: 50px;
}}
</style></head>
<body>
    <img class="bg" src="data:image/png;base64,{img_b64}">
    <div class="overlay">{title_html}{sub_html}{items_html}</div>
</body></html>"""

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        page.screenshot(path=output_path, type="png")
        browser.close()


# ============================================================
# MCP Workflow Reference (for Claude Code)
# ============================================================

MCP_WORKFLOW = """
=== MCP Image Generation Workflow ===

Claude Code uses Chrome MCP tools to generate images.
This is the PREFERRED method (reuses user's logged-in sessions).

=== Overlay Modes ===
- overlay_mode='ai': Text is embedded in the prompt → AI generates text in image directly.
  Best for: ChatGPT (GPT-4o) — good Korean text rendering.
  Result: Text looks naturally integrated, like a professionally designed slide.
- overlay_mode='playwright': Text is overlaid after download via HTML/CSS + Playwright.
  Best for: Gemini, Copilot — unreliable Korean text rendering.
  Result: Reliable but can look "pasted on".
- overlay_mode='auto': Auto-selects based on platform's korean_text_quality.
  ChatGPT → 'ai', Gemini/Copilot → 'playwright'

=== Prompt Building ===
# AI overlay (text baked into image by AI):
prompt = build_prompt(description, style, platform,
                      overlay={'title': '제목', 'subtitle': '부제', 'items': ['태그1', '태그2']},
                      overlay_mode='ai')

# Playwright overlay (text added post-generation):
prompt = build_prompt(description, style, platform)
# → after download: apply_overlay(raw_path, output_path, title=..., subtitle=..., items=...)

--- Gemini (overlay_mode=playwright recommended) ---
1. tabs_context_mcp → get tab info
2. navigate → gemini.google.com/app
3. javascript_tool → find '.ql-editor.textarea', focus
4. computer(type) → enter prompt
5. javascript_tool → click 'button[aria-label="메시지 보내기"]'
6. wait 20-30s
7. javascript_tool → find 'img.image.loaded', get blob URL
8. javascript_tool → canvas.toDataURL → download link → click
9. Bash → copy from Downloads/ to outputs/figures/
10. apply_overlay(raw, final, title=..., subtitle=..., items=...)

--- ChatGPT (overlay_mode=ai recommended) ---
1. tabs_create_mcp → new tab
2. navigate → chatgpt.com
3. build_prompt(..., overlay={title, subtitle, items}, overlay_mode='ai')
4. computer(type) → enter prompt (text instructions already included)
5. javascript_tool → click send button
6. wait 30-60s
7. javascript_tool → find generated image
8. Download via canvas or right-click save
9. No overlay needed — text is already in the image!

--- Copilot (overlay_mode=playwright recommended) ---
1. tabs_create_mcp → new tab
2. navigate → copilot.microsoft.com
3. javascript_tool → find '#userInput', set value with native setter
4. javascript_tool → click 'button[aria-label="메시지 제출"]'
5. wait 20-30s
6. javascript_tool → find large img (naturalWidth > 400)
7. javascript_tool → canvas.toDataURL → download
8. Bash → copy from Downloads/
9. apply_overlay(raw, final, title=..., subtitle=..., items=...)
"""


# ============================================================
# CLI
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description='AI Image Generator')
    sub = parser.add_subparsers(dest='command')

    # platforms command
    sub.add_parser('platforms', help='List available platforms')

    # styles command
    sub.add_parser('styles', help='List style presets')

    # prompt command
    p_prompt = sub.add_parser('prompt', help='Build a prompt')
    p_prompt.add_argument('description', help='Description (Korean or English)')
    p_prompt.add_argument('--style', default='infographic', help='Style preset')
    p_prompt.add_argument('--platform', default='gemini', help='Target platform')

    # overlay command
    p_overlay = sub.add_parser('overlay', help='Apply text overlay to image')
    p_overlay.add_argument('input', help='Input image path')
    p_overlay.add_argument('output', help='Output image path')
    p_overlay.add_argument('--title', help='Title text')
    p_overlay.add_argument('--subtitle', help='Subtitle text')
    p_overlay.add_argument('--items', nargs='+', help='Badge items')

    # scan command
    p_scan = sub.add_parser('scan', help='Scan proposal for figure placeholders')
    p_scan.add_argument('sections_dir', help='Path to sections/ directory')

    args = parser.parse_args()

    if args.command == 'platforms':
        list_platforms()
    elif args.command == 'styles':
        for k, v in STYLE_PRESETS.items():
            print(f"  {k:15s}  {v['use_for']}")
    elif args.command == 'prompt':
        print(build_prompt(args.description, args.style, args.platform))
    elif args.command == 'overlay':
        apply_overlay(args.input, args.output,
                      title=args.title, subtitle=args.subtitle,
                      items=args.items)
        print(f"Overlay applied: {args.output}")
    elif args.command == 'scan':
        figs = proposal_to_prompts(args.sections_dir)
        for fig in figs:
            print(f"  [{fig['placeholder']}]")
            print(f"    style: {fig['style']}")
            print(f"    output: {fig['output_name']}")
            print(f"    prompt: {fig['prompt'][:80]}...")
            print()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
