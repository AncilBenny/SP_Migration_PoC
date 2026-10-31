"""Explicit, fail-closed CIR richText -> accessible destination behavior compiler.

The compiler never reads/executes SharePoint JavaScript. Source formatting is
already sanitized by the rendering boundary. Only simple top-level h2/h3
sections can be converted; ambiguous HTML or source scripts stay review-only.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape, unescape
from html.parser import HTMLParser
import re

MAX_MAPPINGS = 24
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$')

BEHAVIOR_CSS = '''/* Compiler-owned, scoped interactive controls. */
.mig-accordion details { border-bottom: 1px solid #d3dce3; padding: .5rem 0; }
.mig-accordion summary { cursor: pointer; }
.mig-accordion summary h2, .mig-accordion summary h3 { display: inline; font-size: 1.1rem; }
.mig-accordion summary:focus-visible { outline: 2px solid currentColor; outline-offset: 3px; }
.mig-accordion-panel { padding: .5rem 0 1rem; }
.mig-tabs-list[hidden] { display: none; }
.mig-tabs[data-enhanced="true"] .mig-tabs-list { display: flex; flex-wrap: wrap; gap: .5rem; border-bottom: 1px solid #d3dce3; }
.mig-tabs [role="tab"] { font: inherit; color: inherit; border: 1px solid #cbd5de; background: transparent; border-radius: .25rem .25rem 0 0; cursor: pointer; padding: .6rem .9rem; }
.mig-tabs [role="tab"][aria-selected="true"] { border-bottom: 3px solid currentColor; font-weight: bold; }
.mig-tabs [role="tab"]:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }
.mig-tabs [role="tabpanel"]:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }
.mig-tabs[data-enhanced="true"] .mig-tab-panel > h2:first-child, .mig-tabs[data-enhanced="true"] .mig-tab-panel > h3:first-child { display: none; }
'''

# Trusted fixed script compiled with the application, never provided by the page.
# JS enhances existing semantic sections; when JS is unavailable all panels and
# their headings remain visible and readable.
BEHAVIOR_JS = r'''"use strict";
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll('.mig-tabs[data-behavior="tabs"]').forEach((root) => {
    const list = root.querySelector(':scope > .mig-tabs-list');
    const panels = Array.from(root.querySelectorAll(':scope > .mig-tab-panel'));
    if (!list || panels.length < 2) return;
    const buttons = [];
    panels.forEach((panel, index) => {
      const title = panel.firstElementChild;
      if (!title || !/^H[23]$/.test(title.tagName)) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = title.textContent.trim();
      button.id = `${panel.id}-tab`;
      button.setAttribute('role', 'tab');
      button.setAttribute('aria-controls', panel.id);
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', button.id);
      panel.setAttribute('tabindex', '0');
      buttons.push(button);
      list.appendChild(button);
    });
    if (buttons.length !== panels.length) {
      list.replaceChildren();
      return;
    }
    const activate = (index, focus = false) => {
      buttons.forEach((button, i) => {
        const selected = index === i;
        button.setAttribute('aria-selected', String(selected));
        button.tabIndex = selected ? 0 : -1;
        panels[i].hidden = !selected;
      });
      if (focus) buttons[index].focus();
    };
    const initial = Math.min(Number(root.dataset.initialIndex) || 0, buttons.length - 1);
    list.hidden = false;
    root.dataset.enhanced = 'true';
    buttons.forEach((button, i) => {
      button.addEventListener('click', () => activate(i));
      button.addEventListener('keydown', (event) => {
        let index;
        if (event.key === 'ArrowRight') index = (i + 1) % buttons.length;
        else if (event.key === 'ArrowLeft') index = (i - 1 + buttons.length) % buttons.length;
        else if (event.key === 'Home') index = 0;
        else if (event.key === 'End') index = buttons.length - 1;
        else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(i); return; }
        else return;
        event.preventDefault();
        // Manual activation: arrow keys move focus without changing the panel.
        buttons[index].focus();
      });
    });
    activate(initial);
  });
});
'''


def validate_behavior_mappings(raw: object) -> dict[str, dict]:
    if not isinstance(raw, list) or len(raw) > MAX_MAPPINGS:
        raise ValueError('BEHAVIOR_INVALID_PLAN: expected <=24 mappings')
    result = {}
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) - {'nodeId', 'interaction', 'headingLevel', 'initialIndex'}:
            raise ValueError('BEHAVIOR_INVALID_PLAN: unknown mapping fields')
        key = entry.get('nodeId')
        if not isinstance(key, str) or not ID.fullmatch(key) or key in result:
            raise ValueError('BEHAVIOR_INVALID_PLAN: invalid/duplicate nodeId')
        if entry.get('interaction') not in {'accordion', 'tabs'}:
            raise ValueError('BEHAVIOR_INVALID_PLAN: unsupported interaction')
        if type(entry.get('headingLevel', 2)) is not int or entry.get('headingLevel', 2) not in (2, 3):
            raise ValueError('BEHAVIOR_INVALID_PLAN: headingLevel must be 2 or 3')
        if type(entry.get('initialIndex', 0)) is not int or not 0 <= entry.get('initialIndex', 0) <= 20:
            raise ValueError('BEHAVIOR_INVALID_PLAN: invalid initialIndex')
        result[key] = dict(entry)
    return result


class _SectionParser(HTMLParser):
    """Strictly split only sibling heading/content runs; don't attempt DOM repair."""
    def __init__(self, heading: str):
        super().__init__(convert_charrefs=False)
        self.heading = heading
        self.stack: list[str] = []
        self.sections: list[dict] = []
        self.title_open = ''
        self.title_parts: list[str] = []
        self.body_parts: list[str] = []
        self.in_title = False
        self.started = False
        self.closed = False
        self.invalid = False

    def _append(self, raw: str):
        if self.in_title:
            self.title_parts.append(raw)
        elif self.started:
            self.body_parts.append(raw)
        elif raw.strip():
            self.invalid = True

    def _finish(self):
        if not self.started:
            return
        title = ''.join(self.title_parts)
        body = ''.join(self.body_parts)
        extractor = _TextCollector()
        extractor.feed(title)
        if not extractor.text.strip() or not body.strip():
            self.invalid = True
        self.sections.append({'headingOpen': self.title_open, 'headingHtml': title, 'bodyHtml': body})
        self.title_parts = []
        self.body_parts = []

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text()
        if tag == self.heading and not self.stack:
            self._finish()
            self.started = True
            self.title_open = raw
            self.in_title = True
        else:
            self._append(raw)
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self._append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.invalid = True
            return
        self.stack.pop()
        if self.in_title and tag == self.heading and not self.stack:
            self.in_title = False
        else:
            self._append(f'</{tag}>')

    def handle_data(self, data): self._append(data)
    def handle_entityref(self, name): self._append(f'&{name};')
    def handle_charref(self, name): self._append(f'&#{name};')
    def handle_comment(self, data): self.invalid = True

    def sections_from(self, html: str) -> list[dict]:
        self.feed(html)
        self.close()
        self._finish()
        if self.invalid or self.stack or self.in_title or not 2 <= len(self.sections) <= 20:
            raise ValueError('BEHAVIOR_UNSUPPORTED_STRUCTURE: requires 2-20 complete top-level headings with nonempty panels')
        return self.sections


class _TextCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    @property
    def text(self): return ''.join(self.parts)
    def handle_data(self, data): self.parts.append(data)


def compile_behavior(node_id: str, safe_html: str, mapping: dict) -> tuple[str, bool, dict]:
    """Return HTML with original node text once, JS-needed flag, and traceability."""
    level = mapping.get('headingLevel', 2)
    interaction = mapping['interaction']
    sections = _SectionParser(f'h{level}').sections_from(safe_html)
    initial = mapping.get('initialIndex', 0)
    if initial >= len(sections):
        raise ValueError('BEHAVIOR_INVALID_PLAN: initialIndex exceeds panel count')
    slug = sha256(node_id.encode('utf-8')).hexdigest()[:12]
    if interaction == 'accordion':
        blocks = []
        for i, section in enumerate(sections):
            opened = ' open' if i == initial else ''
            blocks.append(f'<details class="mig-accordion-item"{opened}><summary>' + section['headingOpen'] +
                          section['headingHtml'] + f'</h{level}></summary>' +
                          '<div class="mig-accordion-panel">' + section['bodyHtml'] + '</div></details>')
        compiled = '<div class="mig-accordion" data-behavior="accordion">' + ''.join(blocks) + '</div>'
    else:
        panels = []
        for i, section in enumerate(sections):
            panels.append(f'<section id="mig-panel-{slug}-{i}" class="mig-tab-panel">' +
                          section['headingOpen'] + section['headingHtml'] + f'</h{level}>' +
                          section['bodyHtml'] + '</section>')
        compiled = (f'<div class="mig-tabs" data-behavior="tabs" data-initial-index="{initial}">' +
                    '<div class="mig-tabs-list" role="tablist" aria-label="Content sections" hidden></div>' +
                    ''.join(panels) + '</div>')
    return compiled, interaction == 'tabs', {'nodeId': node_id, 'interaction': interaction,
                                            'panels': len(sections), 'headingLevel': level,
                                            'review': 'visual-and-keyboard-browser-validation-required'}
