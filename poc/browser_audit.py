"""Optional browser-render regression gate for generated HTML/CSS.

No source visual baseline is implied. Only local file URLs are opened; all
network requests are blocked. Screenshots and metrics are evidence for review.
Requires optional Playwright and an installed Chromium browser.
"""
from __future__ import annotations

from hashlib import sha256
import json
import base64
import mimetypes
from urllib.parse import urlsplit, unquote
from pathlib import Path
import shutil

VIEWPORTS = {'desktop': (1440, 900), 'mobile': (390, 844)}


def audit_browser_page(html_file: Path, output: Path) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError('Browser audit requires Playwright: pip install playwright') from e
    html_file = Path(html_file).resolve()
    if html_file.name != 'index.html' or not html_file.is_file():
        raise ValueError('BROWSER_AUDIT_INPUT: specify an existing index.html')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    outcomes = {}
    html_text = html_file.read_text(encoding='utf-8')
    if len(html_text) > 2_000_000:
        raise ValueError('BROWSER_AUDIT_LIMIT: HTML exceeds 2 MB')
    styles = []
    for file_name in ('style.css', 'source-styles.css'):
        css_path = html_file.parent / file_name
        if css_path.is_file() and not css_path.is_symlink():
            if css_path.stat().st_size > 200_000:
                raise ValueError('BROWSER_AUDIT_LIMIT: CSS exceeds 200 KB')
            styles.append(css_path.read_text(encoding='utf-8'))
    with sync_playwright() as playwright:
        binary = shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome')
        browser = playwright.chromium.launch(headless=True, executable_path=binary) if binary else playwright.chromium.launch(headless=True)
        try:
            for label, (width, height) in VIEWPORTS.items():
                context = browser.new_context(viewport={'width':width,'height':height}, device_scale_factor=1,
                                              reduced_motion='reduce', java_script_enabled=False)
                context.route('**/*', lambda route: route.abort())  # no network, including loopback
                page = context.new_page()
                try:
                    # Browser evaluates only static generated content. No file:// or HTTP navigation.
                    page.set_content(html_text, wait_until='domcontentloaded', timeout=15000)
                    for css in styles:
                        # DOM test harness evaluation is allowed; page JS remains disabled.
                        page.evaluate('''(css) => { const s = document.createElement("style");
                            s.textContent = css; document.head.append(s); }''', css)
                    # Embed only validated local image bytes, avoiding file/http requests.
                    images = page.evaluate('() => [...document.images].map(im => im.getAttribute("src") || "")')
                    for image_src in images:
                        pieces = urlsplit(image_src)
                        if pieces.scheme or pieces.netloc or not pieces.path or pieces.path.startswith('/'):
                            continue
                        path_parts = Path(unquote(pieces.path)).parts
                        if '..' in path_parts:
                            continue
                        asset = html_file.parent / Path(*path_parts)
                        if not asset.is_file() or asset.is_symlink() or not asset.resolve().is_relative_to(html_file.parent):
                            continue
                        mime = {'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg',
                                '.gif':'image/gif','.webp':'image/webp','.svg':'image/svg+xml'}.get(asset.suffix.lower())
                        if not mime or asset.stat().st_size > 2_000_000:
                            continue
                        data_url = f'data:{mime};base64,' + base64.b64encode(asset.read_bytes()).decode('ascii')
                        page.evaluate('''([src, data]) => { for (const im of document.images) {
                            if (im.getAttribute("src") === src) im.src = data;
                        }}''', [image_src, data_url])
                    metrics = page.evaluate('''() => ({
                      viewportWidth: window.innerWidth,
                      documentWidth: document.documentElement.scrollWidth,
                      mainPresent: Boolean(document.querySelector('main')),
                      headingCount: document.querySelectorAll('h1,h2,h3,h4,h5,h6').length,
                      brokenLocalImages: [...document.images].filter(im => !im.naturalWidth && !/^https?:/.test(im.src)).length,
                      firstHeadingColor: getComputedStyle(document.querySelector('h1,h2') || document.body).color,
                      firstHeadingFontSize: getComputedStyle(document.querySelector('h1,h2') || document.body).fontSize
                    })''')
                    # Trace ONLY compiler-emitted IR markers. Never record page text,
                    # URLs, screenshot pixels or arbitrary source selectors here.
                    component_geometry = page.evaluate('''() =>
                      [...document.querySelectorAll('[data-ir-id]')].slice(0, 200)
                        .map(el => {
                          const r = el.getBoundingClientRect();
                          const css = getComputedStyle(el);
                          return {
                            nodeId: el.getAttribute('data-ir-id'),
                            elementTag: el.tagName.toLowerCase(),
                            rect: {
                              x: Math.round(r.left + window.scrollX),
                              y: Math.round(r.top + window.scrollY),
                              width: Math.round(r.width),
                              height: Math.round(r.height)
                            },
                            styleProbe: {
                              fontSize: css.fontSize,
                              lineHeight: css.lineHeight,
                              display: css.display
                            }
                          };
                        }).filter(item => item.rect.width > 0 && item.rect.height > 0)
                    ''')
                    screenshot = page.screenshot(full_page=True, animations='disabled', timeout=10000)
                    (output / f'{label}.png').write_bytes(screenshot)
                    outcomes[label] = {
                        **metrics,
                        'horizontalOverflow': metrics['documentWidth'] > width + 1,
                        'screenshot':f'{label}.png',
                        'componentGeometry':component_geometry,
                        'sha256':sha256(screenshot).hexdigest(),
                    }
                finally:
                    context.close()
        finally:
            browser.close()
    issues = [key for key, result in outcomes.items() if result['horizontalOverflow'] or not result['mainPresent'] or result['brokenLocalImages']]
    report = {
        'version':'browser-audit-0.1', 'localHtml':html_file.name,
        'viewports':outcomes, 'structuralPassed':not issues,
        'reviewRequired':True,
        'scope':'Static offline generated HTML/CSS; JS disabled; external network blocked; no matched SharePoint visual baseline',
        'issues':issues,
    }
    (output / 'browser-audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report
