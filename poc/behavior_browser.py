"""Optional isolated browser acceptance of compiler-owned destination interactions.

Never executes SharePoint source JavaScript and never reaches the network.
This is a target-functionality smoke test, NOT original-source parity.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from .behavior_compiler import BEHAVIOR_JS
from .behavior_evidence import compare_destination_behavior


def audit_behavior_browser(ir: dict, html: str, profile: dict, mapping_report: dict) -> dict:
    from .contracts import validate_ir
    from .mapping import validate_profile
    validate_ir(ir); validate_profile(profile)
    static = compare_destination_behavior(ir, html, profile, mapping_report)
    if not static['passed']:
        raise ValueError('BEHAVIOR_STATIC_CHECK_FAILED')
    if len(html) > 3_000_000:
        raise ValueError('BEHAVIOR_HTML_LIMIT')
    # The generated site is a *source* for the browser harness, not a place to
    # execute arbitrary scripts. Remove the one known fixed asset and reject any
    # remaining script or browser-executable markup before enabling JS.
    html = re.sub(r'<script\s+src=["\']behavior\.js["\']\s+defer\s*>\s*</script\s*>', '', html, flags=re.I)
    if re.search(r'<\s*(?:script|iframe|object|embed|svg|math)\b|\bon[a-z]{3,}\s*=|javascript:|\bsrcdoc\s*=', html, flags=re.I):
        raise ValueError('BEHAVIOR_UNTRUSTED_BROWSER_INPUT')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError('BEHAVIOR_BROWSER_REQUIRES_PLAYWRIGHT') from exc

    checks=[]
    with sync_playwright() as playwright:
        import shutil
        binary = shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome')
        browser = playwright.chromium.launch(headless=True, executable_path=binary) if binary else playwright.chromium.launch(headless=True)
        try:
            for width,height in ((1440,900),(390,844)):
                context = browser.new_context(viewport={'width':width,'height':height}, reduced_motion='reduce')
                context.route('**/*', lambda route: route.abort())
                page = context.new_page()
                errors=[]
                page.on('pageerror', lambda error: errors.append('JavaScript runtime error'))
                try:
                    page.set_content(html, wait_until='load', timeout=15000)
                    # Only application-owned and reviewed JavaScript is injected.
                    page.add_script_tag(content=BEHAVIOR_JS)
                    page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
                    for entry in static['destinationChecks']:
                        if entry['status'] != 'pass' or entry['nodeId']=='__document__': continue
                        kind=entry['interaction']
                        root=page.locator(f'[data-behavior="{kind}"]')
                        if root.count()!=1:
                            errors.append('Expected one '+kind+' root')
                            continue
                        control=root.first
                        if kind=='accordion':
                            details=control.locator('details')
                            details.nth(0).locator('summary').click(timeout=2500)
                            if details.nth(0).get_attribute('open') is not None:
                                errors.append('Accordion failed to close')
                            details.nth(0).locator('summary').click(timeout=2500)
                            if details.nth(0).get_attribute('open') is None:
                                errors.append('Accordion failed to reopen')
                        elif kind=='tabs':
                            tabs=control.locator('[role="tab"]')
                            if tabs.count() != entry['expectedItems']:
                                errors.append('Tabs were not enhanced')
                                continue
                            tabs.nth(1).click(timeout=2500)
                            if tabs.nth(1).get_attribute('aria-selected') != 'true':
                                errors.append('Tab click did not activate')
                            tabs.nth(1).press('ArrowRight')
                            if tabs.nth(2 if tabs.count()>2 else 0).evaluate('(el) => el === document.activeElement') is not True:
                                errors.append('Tab arrow key did not move focus')
                        elif kind=='filterLinks':
                            search=control.locator('input[type="search"]')
                            if not search.is_visible():
                                errors.append('Filter was not enhanced')
                            else:
                                search.fill('zzzz-no-matching-resource')
                                if control.locator('[data-filter-item]:visible').count()!=0:
                                    errors.append('Filter failed to hide unmatched items')
                                search.fill('')
                                if control.locator('[data-filter-item]:visible').count()!=entry['expectedItems']:
                                    errors.append('Cleared filter did not restore all items')
                        elif kind=='toc':
                            anchors=control.locator('nav a[href^="#mig-section-"]')
                            if anchors.count()!=entry['expectedItems']:
                                errors.append('On-page navigation anchors missing')
                    checks.append({'viewport':width,'passed':not errors,'errors':errors})
                finally:
                    context.close()
        finally:
            browser.close()
    return {'version':'behavior-browser-0.1','checks':checks, 'passed':all(x['passed'] for x in checks),
            'reviewRequired':True,'sourceBehaviorFidelity':'not-evaluated-no-matched-sharepoint-baseline',
            'note':'Generated controls executed in isolated Chromium. Source behavior and appearance not compared.'}


def audit_behavior_browser_files(ir_file: Path, html_file: Path, profile_file: Path, report_file: Path, out_file: Path) -> dict:
    ir=json.loads(ir_file.read_text(encoding='utf-8'))
    html=html_file.read_text(encoding='utf-8')
    profile=json.loads(profile_file.read_text(encoding='utf-8'))
    report=json.loads(report_file.read_text(encoding='utf-8'))
    result=audit_behavior_browser(ir,html,profile,report)
    out_file.parent.mkdir(parents=True,exist_ok=True)
    out_file.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result
