"""Offline, reviewable stylesheet migration workbench.

This tool NEVER fetches @import or url() resources or copies arbitrary CSS.
A tiny semantic selector/declaration vocabulary is intentionally compilable;
unsupported styles and at-rules are recorded for a human mapping decision.
Output is scoped to rich text, not a claim of CSSOM/cascade equivalence.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from html.parser import HTMLParser
import re

from .style_compiler import compile_declarations, tinycss2

MAX_CSS_BYTES = 200_000
MAX_CSS_NODES = 1200
MAX_SELECTOR_CHARS = 160
ALLOWED_TAGS = frozenset({
    'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'ul', 'ol', 'li',
    'strong', 'em', 'span', 'blockquote', 'figure', 'figcaption',
    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'img', 'code', 'pre'
})
# Deliberately narrow: no :has, :not, pseudo-selectors, IDs, attribute selectors,
# arbitrary classes, global element rules, nesting or combinators except descendants.
ALLOWED_SELECTOR = re.compile(r'^[a-z][a-z0-9-]*(?:\s+[a-z][a-z0-9-]*){0,2}$')
ALLOWED_MEDIA = re.compile(r'^\(\s*(min|max)-width\s*:\s*(\d{2,4})px\s*\)$', re.I)
HEX_TOKEN = re.compile(r'^#[0-9a-f]{3}(?:[0-9a-f]{3}|[0-9a-f]{5})?$', re.I)

# Explicit source selectors map to renderer-owned components; source selectors
# never become destination CSS selectors or run as browser code.
TARGET_COMPONENTS = {
    'content.heading1': ('.target-body h1', 'target-body', 'h1'),
    'content.heading2': ('.target-body h2', 'target-body', 'h2'),
    'content.heading3': ('.target-body h3', 'target-body', 'h3'),
    'content.paragraph': ('.target-body p', 'target-body', 'p'),
    'content.link': ('.target-body a', 'target-body', 'a'),
    'content.list': ('.target-body ul', 'target-body', 'ul'),
    'resource.card': ('.target-resource', 'target-resource', None),
    'resource.link': ('.target-resource a', 'target-resource', 'a'),
    'media.caption': ('.target-media figcaption', 'target-media', 'figcaption'),
    'page.title': ('.target-header h1', 'target-header', 'h1'),
}
MAX_SELECTOR_MAPPINGS = 64
SOURCE_SELECTOR_CHARS = re.compile(r'^[.#a-zA-Z][a-zA-Z0-9_.# >-]{0,159}$')
VOID_TAGS = frozenset({'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'})


def _source_selector(raw: str) -> str:
    if not isinstance(raw, str):
        raise ValueError('CSS_MAPPING_INVALID_SOURCE_SELECTOR')
    normalized = ' '.join(raw.lower().split())
    if not SOURCE_SELECTOR_CHARS.fullmatch(normalized):
        raise ValueError('CSS_MAPPING_INVALID_SOURCE_SELECTOR')
    return normalized


def validate_selector_map(mapping: dict | None) -> dict[str, str]:
    """Exact-match, review-only selector mapping; output selectors are fixed."""
    if mapping is None:
        return {}
    if not isinstance(mapping, dict) or set(mapping) != {'version', 'mappings'} or mapping['version'] != '1.0':
        raise ValueError('CSS_MAPPING_INVALID_FORMAT')
    entries = mapping['mappings']
    if not isinstance(entries, list) or len(entries) > MAX_SELECTOR_MAPPINGS:
        raise ValueError('CSS_MAPPING_LIMIT_EXCEEDED')
    validated: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'sourceSelector', 'targetComponent'}:
            raise ValueError('CSS_MAPPING_INVALID_ENTRY')
        source = _source_selector(entry['sourceSelector'])
        target = entry['targetComponent']
        if not isinstance(target, str) or target not in TARGET_COMPONENTS:
            raise ValueError('CSS_MAPPING_UNKNOWN_COMPONENT')
        if source in validated:
            raise ValueError('CSS_MAPPING_DUPLICATE_SELECTOR')
        validated[source] = target
    return validated


class _SemanticTagScanner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags: Counter[str] = Counter()
        self.components: set[str] = set()
        self.stack: list[tuple[str, set[str]]] = []

    def handle_starttag(self, tag, attrs):
        if tag in ALLOWED_TAGS:
            self.tags[tag] += 1
        classes = set()
        for key, value in attrs:
            if key == 'class' and isinstance(value, str):
                classes.update(value.split())
        parent_classes = set().union(*(part[1] for part in self.stack)) if self.stack else set()
        context = parent_classes | classes
        for component, (_selector, required_class, leaf) in TARGET_COMPONENTS.items():
            if required_class in context and (leaf is None or tag == leaf):
                self.components.add(component)
        if tag not in VOID_TAGS:
            self.stack.append((tag, classes))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


def _safe_selector(raw: str) -> str | None:
    # Only semantic element selectors whose meaning survives source -> CIR.
    selector = ' '.join(raw.lower().split())
    if len(selector) > MAX_SELECTOR_CHARS or not ALLOWED_SELECTOR.fullmatch(selector):
        return None
    parts = selector.split(' ')
    return selector if all(part in ALLOWED_TAGS for part in parts) else None


def _safe_media(condition: str) -> str | None:
    match = ALLOWED_MEDIA.fullmatch(condition.strip())
    if not match or not 240 <= int(match[2]) <= 3840:
        return None
    return f'({match[1].lower()}-width: {int(match[2])}px)'


def compile_reviewed_css(source_css: str, rendered_html: str = '', *, selector_map: dict | None = None) -> tuple[str, dict]:
    """Return scoped safe CSS and diagnostic manifest for an EXPLICIT source CSS file.

    A parsed source selector is only a *candidate*: matching element names does
    not establish computed style parity. @media groups are retained in order,
    never flattened; the untrusted original CSS is never embedded in output.
    """
    if tinycss2 is None:
        raise RuntimeError('CSS workbench requires tinycss2')
    explicit_mappings = validate_selector_map(selector_map)
    if not isinstance(source_css, str) or len(source_css.encode('utf-8')) > MAX_CSS_BYTES:
        raise ValueError('CSS_WORKBENCH_LIMIT: source CSS exceeds 200 KB')
    if not isinstance(rendered_html, str) or len(rendered_html) > 2_000_000:
        raise ValueError('CSS_WORKBENCH_LIMIT: rendered HTML exceeds 2 MB')
    scanner = _SemanticTagScanner()
    scanner.feed(rendered_html)
    scanner.close()
    observed_tags = dict(sorted(scanner.tags.items()))
    counts: Counter[str] = Counter()
    blocked: Counter[str] = Counter()
    rules: list[dict] = []
    colors: Counter[str] = Counter()
    media_queries: set[str] = set()
    emitted_rules: list[str] = []
    mapped_selector_hits: Counter[str] = Counter()
    rule_budget = 0

    def walk(nodes, media=None, depth=0):
        nonlocal rule_budget
        if depth > 5:
            raise ValueError('CSS_WORKBENCH_LIMIT: nesting exceeds 5')
        for rule in nodes:
            if rule.type in {'comment', 'whitespace'}:
                continue
            rule_budget += 1
            if rule_budget > MAX_CSS_NODES:
                raise ValueError('CSS_WORKBENCH_LIMIT: too many rules')
            if rule.type == 'error':
                blocked['parse-error'] += 1
                continue
            if rule.type == 'at-rule':
                name = rule.lower_at_keyword
                counts['@'+name] += 1
                if name == 'media' and rule.content is not None:
                    condition = tinycss2.serialize(rule.prelude).strip()
                    media_queries.add(condition[:160])
                    safe = _safe_media(condition)
                    if safe and media is None:
                        walk(tinycss2.parse_rule_list(rule.content, skip_whitespace=True, skip_comments=True), safe, depth+1)
                    else:
                        blocked['conditional-media-unhandled'] += 1
                    continue
                if name == 'import':
                    blocked['external-import-not-acquired'] += 1
                elif name in {'container', 'supports', 'layer', 'scope', 'font-face', 'keyframes', 'property'}:
                    blocked['@'+name+'-requires-review'] += 1
                else:
                    blocked['@'+name+'-unsupported'] += 1
                continue
            if rule.type != 'qualified-rule':
                blocked['unknown-rule'] += 1
                continue
            raw_selector = tinycss2.serialize(rule.prelude).strip()
            counts['styleRules'] += 1
            # Explicit exact selector mappings take priority; the untrusted
            # source selector is never evaluated in the destination browser.
            source_key = ' '.join(raw_selector.lower().split())
            target_component = explicit_mappings.get(source_key)
            selector = _safe_selector(raw_selector)
            if target_component:
                mapped_selector_hits[source_key] += 1
                scoped = TARGET_COMPONENTS[target_component][0]
                if rendered_html and target_component not in scanner.components:
                    blocked['target-component-not-present'] += 1
                    rules.append({'selectorHash':sha256(raw_selector.encode('utf-8')).hexdigest()[:12],
                                  'targetComponent':target_component, 'decision':'review',
                                  'reason':'target-component-not-present'})
                    continue
            elif selector is None:
                blocked['selector-not-portable'] += 1
                rules.append({'selectorHash':sha256(raw_selector.encode('utf-8')).hexdigest()[:12], 'decision':'review', 'reason':'selector-not-portable'})
                continue
            else:
                scoped = ':is(.rich-text,.target-body) ' + selector
            if not rule.content:
                blocked['empty-rule'] += 1
                continue
            values = tinycss2.parse_declaration_list(rule.content, skip_whitespace=True, skip_comments=True)
            serialized = []
            for decl in values:
                if decl.type == 'declaration':
                    serialized.append(tinycss2.serialize([decl]))
                else:
                    blocked['nested-or-invalid-declaration'] += 1
            safe, rejected = compile_declarations(';'.join(serialized))
            counts['allowedDeclarations'] += len(safe)
            for name in rejected:
                blocked['declaration-'+str(name)[:45]] += 1
            if not safe:
                blocked['rule-without-safe-properties'] += 1
                rules.append(({'sourceSelectorHash':sha256(raw_selector.encode('utf-8')).hexdigest()[:12],
                               'targetComponent':target_component} if target_component else {'selector':selector}) |
                             {'decision':'review','reason':'no-safe-properties'})
                continue
            for prop, value in safe.items():
                if prop in {'color','background-color'} and HEX_TOKEN.fullmatch(value):
                    colors[value] += 1
            statement = scoped + ' { ' + ' '.join(f'{k}: {v};' for k,v in safe.items()) + ' }'
            if media:
                statement = '@media ' + media + ' {\n  ' + statement + '\n}'
            emitted_rules.append(statement)
            entry = {'decision':'mapped-candidate' if target_component else 'candidate',
                     'targetSelector':scoped, 'media':media,
                     'properties':sorted(safe), 'rejectedDeclarations':len(rejected),
                     'lastTagObserved': bool(observed_tags.get(selector.split()[-1])) if not target_component else target_component in scanner.components}
            if target_component:
                entry['sourceSelectorHash'] = sha256(raw_selector.encode('utf-8')).hexdigest()[:12]
                entry['targetComponent'] = target_component
                counts['mappedRules'] += 1
            else:
                entry['selector'] = selector
            rules.append(entry)
            counts['candidateRules'] += 1

    walk(tinycss2.parse_stylesheet(source_css, skip_comments=True, skip_whitespace=True))
    css = ('/* Review-only CSS candidates. NOT verified against source computed styles. */\n'
           '/* Scoped to reviewed output components; never imports runtime code. */\n'
           + '\n\n'.join(emitted_rules) + ('\n' if emitted_rules else ''))
    report = {
        'version':'css-workbench-0.1',
        'sourceSha256':sha256(source_css.encode('utf-8')).hexdigest(),
        'selectorMapping':{'configured':len(explicit_mappings),
                           'policy':'explicit-component-mappings-review-only-not-applied',
                           'matched':len(mapped_selector_hits),
                           'unmatchedSourceSelectorHashes':sorted(sha256(x.encode('utf-8')).hexdigest()[:12] for x in explicit_mappings if x not in mapped_selector_hits),
                           'knownTargetComponents':sorted(TARGET_COMPONENTS)},
        'result':'review-required',
        'sourceCounts':dict(sorted(counts.items())),
        'blockedFeatures':dict(sorted(blocked.items())),
        'mediaConditions':sorted(media_queries),
        'observedOutputTags':observed_tags,
        'candidateColorTokens':[{'color':color,'references':count} for color,count in sorted(colors.items())],
        'candidateRules':rules[:250],
        'emittedRuleCount':len(emitted_rules),
        'confidence':'static-semantic-candidates-only',
        'limitations':['Not a computed-style or cascade comparison',
                       'No unreviewed SharePoint selectors, SPFx styles, imports, remote CSS or runtime scripts are carried over',
                       'Explicit mapping candidates use renderer-owned component selectors only; no automatic application',
                       'Manual review plus rendered screenshot checks required before applying CSS'],
    }
    return css, report
