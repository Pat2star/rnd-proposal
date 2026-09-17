"""
Gemini NanoBanana image generation via Playwright browser automation.
Generates AI images through gemini.google.com (requires logged-in Chrome profile).

Usage:
    from gemini_image import generate_image
    generate_image("A futuristic robot lab", "output.png")

    # With text overlay
    generate_image("A futuristic robot lab", "output.png",
                   overlay_title="AI 연구 시스템",
                   overlay_subtitle="멀티에이전트 협업 구조")
"""

import os
import time
import shutil


def generate_image(prompt, output_path, timeout=60,
                   overlay_title=None, overlay_subtitle=None,
                   overlay_items=None, platform='gemini'):
    """Generate an AI image via Gemini and optionally add text overlay.

    Args:
        prompt: English image generation prompt
        output_path: Where to save the final PNG
        timeout: Max seconds to wait for image generation
        overlay_title: Korean title text to overlay (top-left)
        overlay_subtitle: Korean subtitle text
        overlay_items: List of label strings for bottom overlay badges
        platform: 'gemini' or 'copilot'
    """
    from playwright.sync_api import sync_playwright

    # Step 1: Generate image via browser
    raw_path = output_path.replace('.png', '_raw.png')

    if platform == 'gemini':
        _generate_via_gemini(prompt, raw_path, timeout)
    elif platform == 'copilot':
        _generate_via_copilot(prompt, raw_path, timeout)
    else:
        raise ValueError(f"Unknown platform: {platform}")

    # Step 2: Apply text overlay if requested
    if overlay_title or overlay_subtitle or overlay_items:
        _apply_overlay(raw_path, output_path,
                       overlay_title, overlay_subtitle, overlay_items)
    else:
        shutil.move(raw_path, output_path)

    return os.path.exists(output_path)


def _generate_via_gemini(prompt, output_path, timeout=60):
    """Navigate to Gemini, enter prompt, wait for image, download it."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        # Connect to user's Chrome with existing login
        browser = pw.chromium.launch(
            headless=False,
            channel="chrome",
        )
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://gemini.google.com/app", wait_until="networkidle",
                  timeout=30000)

        # Find and fill the prompt input
        editor = page.wait_for_selector('.ql-editor.textarea', timeout=15000)
        editor.click()
        page.keyboard.type(prompt, delay=10)
        time.sleep(0.5)

        # Click send button
        send_btn = page.wait_for_selector(
            'button[aria-label*="보내기"], button[aria-label*="Send"]',
            timeout=5000
        )
        send_btn.click()

        # Wait for image to appear
        img_selector = 'img.image.loaded, img.image.animate.loaded'
        page.wait_for_selector(img_selector, timeout=timeout * 1000)
        time.sleep(3)  # extra wait for full render

        # Download image via canvas
        img = page.query_selector(img_selector)
        if img:
            data_url = page.evaluate("""(img) => {
                const canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth;
                canvas.height = img.naturalHeight;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0);
                return canvas.toDataURL('image/png');
            }""", img)

            # Save data URL to file
            import base64
            header = 'data:image/png;base64,'
            if data_url.startswith(header):
                img_data = base64.b64decode(data_url[len(header):])
                os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(img_data)

        browser.close()


def _generate_via_copilot(prompt, output_path, timeout=60):
    """Navigate to Copilot, enter prompt, wait for image, download it."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, channel="chrome")
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://copilot.microsoft.com", wait_until="networkidle",
                  timeout=30000)

        # Find input
        editor = page.wait_for_selector(
            'textarea, [contenteditable="true"], #searchbox',
            timeout=15000
        )
        editor.click()
        page.keyboard.type(prompt, delay=10)
        time.sleep(0.5)

        # Send
        page.keyboard.press("Enter")

        # Wait for generated image
        page.wait_for_selector('img[alt*="Generated"], img[data-testid]',
                               timeout=timeout * 1000)
        time.sleep(5)

        # Download first large image
        imgs = page.query_selector_all('img')
        for img in imgs:
            w = img.evaluate('el => el.naturalWidth')
            if w and w > 400:
                data_url = page.evaluate("""(img) => {
                    const canvas = document.createElement('canvas');
                    canvas.width = img.naturalWidth;
                    canvas.height = img.naturalHeight;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0);
                    return canvas.toDataURL('image/png');
                }""", img)
                import base64
                header = 'data:image/png;base64,'
                if data_url.startswith(header):
                    img_data = base64.b64decode(data_url[len(header):])
                    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
                    with open(output_path, 'wb') as f:
                        f.write(img_data)
                break

        browser.close()


def _generate_via_mcp(prompt, output_path, timeout=60, platform='gemini'):
    """Generate image using MCP (Claude-in-Chrome) — for use within Claude Code.

    This is the preferred method when running inside Claude Code,
    as it reuses the user's already-logged-in browser session.
    Cannot be called from standalone scripts.
    """
    # This function documents the MCP workflow for reference.
    # Actual MCP calls are made by Claude Code directly.
    raise NotImplementedError(
        "MCP generation is handled by Claude Code directly. "
        "Use generate_image() with platform='gemini' for standalone use, "
        "or let Claude Code use the MCP tools for browser automation."
    )


def _apply_overlay(input_path, output_path, title=None, subtitle=None,
                   items=None):
    """Apply Korean text overlay on the generated image using HTML+Playwright."""
    from playwright.sync_api import sync_playwright
    import base64

    with open(input_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode()

    # Build overlay HTML
    items_html = ''
    if items:
        badges = ''.join(
            f'<span class="badge">{item}</span>' for item in items
        )
        items_html = f'<div class="items">{badges}</div>'

    title_html = f'<div class="title">{title}</div>' if title else ''
    sub_html = f'<div class="subtitle">{subtitle}</div>' if subtitle else ''

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: 1024px; height: 572px; position: relative; overflow: hidden;
    font-family: 'Noto Sans KR', sans-serif;
}}
.bg {{
    width: 100%; height: 100%;
    object-fit: cover;
}}
.overlay {{
    position: absolute; top: 0; left: 0; width: 58%; height: 100%;
    background: linear-gradient(135deg, rgba(0,0,0,0.70) 0%, rgba(0,0,0,0.25) 65%, transparent 100%);
    padding: 40px 36px;
    display: flex; flex-direction: column; justify-content: center;
}}
.title {{
    color: white; font-size: 32px; font-weight: 900;
    line-height: 1.35; margin-bottom: 14px;
    text-shadow: 0 2px 8px rgba(0,0,0,0.4);
    white-space: pre-line;
}}
.subtitle {{
    color: rgba(255,255,255,0.88); font-size: 16px; font-weight: 400;
    line-height: 1.6; margin-bottom: 20px;
    text-shadow: 0 1px 4px rgba(0,0,0,0.3);
    white-space: pre-line;
}}
.items {{
    display: flex; flex-wrap: wrap; gap: 10px;
}}
.badge {{
    background: rgba(255,255,255,0.2);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,0.3);
    color: white; font-size: 14px; font-weight: 700;
    padding: 8px 18px; border-radius: 50px;
}}
</style></head>
<body>
    <img class="bg" src="data:image/png;base64,{img_b64}">
    <div class="overlay">
        {title_html}
        {sub_html}
        {items_html}
    </div>
</body></html>"""

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1024, "height": 572})
        page.set_content(html)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        page.screenshot(path=output_path, type="png")
        browser.close()

    # Clean up raw file
    if os.path.exists(input_path) and input_path != output_path:
        os.remove(input_path)


def build_prompt(description, style='infographic'):
    """Build an English image generation prompt from a Korean description.

    Args:
        description: Korean description of what the image should show
        style: 'infographic', 'diagram', 'concept', 'process'

    Returns:
        English prompt string optimized for NanoBanana/DALL-E
    """
    style_map = {
        'infographic': (
            "professional infographic-style 3D illustration, "
            "clean modern design, tech corporate aesthetic, "
            "blue gradient background with subtle grid pattern"
        ),
        'diagram': (
            "clean technical diagram illustration, "
            "flat design with isometric elements, "
            "white background with subtle shadows"
        ),
        'concept': (
            "conceptual illustration with metaphorical scene, "
            "3D rendered characters and objects, "
            "warm professional lighting, modern tech setting"
        ),
        'process': (
            "process flow illustration with connected stages, "
            "futuristic conveyor belt or pipeline metaphor, "
            "clean 3D rendered style, professional colors"
        ),
    }

    style_desc = style_map.get(style, style_map['infographic'])

    return (
        f"Generate a wide 16:9 {style_desc}. "
        f"The scene depicts: {description}. "
        f"Leave empty space at top-left corner for text overlay. "
        f"Professional and visually impressive, suitable for a research proposal presentation. "
        f"No text or letters in the image."
    )
