"""Strict, deterministic presentation compiler for untrusted page fragments.

Only a tiny reviewed CSS *declaration* vocabulary is supported; no selectors,
imports, URLs, scripts or CSS functions are emitted. Never compile arbitrary
SharePoint/third-party CSS or JS into executable output.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from html.parser import HTMLParser
import json
import re

try:
    import tinycss2
except ImportError:  # no silent fallback to brittle CSS splitting
    tinycss2 = None

MAX_STYLE_LENGTH = 4096
MAX_RULES_PER_PAGE = 256
STYLE_CLASS = re.compile(r'^mig-s-[0-9a-f]{12}$')
HEX_COLOR = re.compile(r'^#[0-9a-f]{3}(?:[0-9a-f]{3}|[0-9a-f]{5})?$', re.I)
SIZE = re.compile(r'^(\d+(?:\.\d{1,2})?)(px|rem)$')
WEIGHT = re.compile(r'^(?:normal|bold|[1-9]00)$')
COLORS = {'black','white','red','blue','green','gray','grey','navy','teal','maroon','purple','silver','transparent','currentcolor'}
TEXT_ALIGN = {'left','right','center','justify','start','end'}


def compile_declarations(raw: str) -> tuple[dict[str,str], list[str]]:
    """Return safe normalized CSS declarations and rejected property *names* only."""
    if tinycss2 is None:
        raise RuntimeError('CSS compiler requires tinycss2: pip install -r requirements.txt')
    if not isinstance(raw, str) or len(raw) > MAX_STYLE_LENGTH:
        return {}, ['style-too-large-or-invalid']
    accepted: dict[str,str] = {}
    rejected: list[str] = []
    for token in tinycss2.parse_declaration_list(raw, skip_whitespace=True, skip_comments=True):
        if token.type != 'declaration':
            rejected.append('invalid-css-rule')
            continue
        name = token.lower_name
        value = tinycss2.serialize(token.value).strip().lower()
        if token.important or len(value) > 96 or not value or any(c in value for c in '{};\\'):
            rejected.append(name)
            continue
        valid = False
        if name in {'color', 'background-color'}:
            valid = bool(HEX_COLOR.fullmatch(value) or value in COLORS)
        elif name == 'font-weight':
            valid = bool(WEIGHT.fullmatch(value))
        elif name == 'font-style':
            valid = value in {'normal','italic','oblique'}
        elif name == 'text-decoration':
            valid = value in {'none','underline','line-through'}
        elif name == 'text-align':
            valid = value in TEXT_ALIGN
        elif name in {'font-size', 'margin-top', 'margin-bottom', 'padding-top', 'padding-bottom'}:
            m = SIZE.fullmatch(value)
            valid = bool(m and 0 <= float(m[1]) <= (72 if m[2] == 'px' else 4))
            if name == 'font-size' and m:
                valid = valid and float(m[1]) >= (8 if m[2] == 'px' else 0.5)
        elif name == 'line-height':
            valid = bool(re.fullmatch(r'\d+(?:\.\d{1,2})?', value) and 1 <= float(value) <= 2.5)
        if valid:
            accepted[name] = value
        else:
            rejected.append(name)
    return dict(sorted(accepted.items())), rejected


def class_for_style(declarations: dict[str,str]) -> str:
    canonical = json.dumps(dict(sorted(declarations.items())), sort_keys=True, separators=(',',':'))
    return 'mig-s-' + sha256(canonical.encode('utf-8')).hexdigest()[:12]


class _ClassScanner(HTMLParser):
    def __init__(self):
        super().__init__()
        self.classes: set[str] = set()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == 'class' and value:
                # Source-derived arbitrary classes are not part of the CIR contract.
                if not STYLE_CLASS.fullmatch(value):
                    raise ValueError('STYLE_CONTRACT_INVALID: unrecognized class')
                self.classes.add(value)


def verified_rules(ir: dict) -> tuple[dict[str,dict[str,str]], dict]:
    """Treat CIR as untrusted; reject forged CSS selectors/values and class hashes."""
    rules = {}
    nodes = [(ir['tree'], 0)]
    refs = 0
    while nodes:
        node, depth = nodes.pop()
        if depth > 64:
            raise ValueError('STYLE_CONTRACT_INVALID: excessive nesting')
        nodes.extend((c, depth+1) for c in node.get('children', []))
        local_classes = set()
        for record in (node.get('props') or {}).get('styleRules', []):
            if not isinstance(record, dict) or set(record) != {'className', 'declarations'}:
                raise ValueError('STYLE_CONTRACT_INVALID: invalid record fields')
            declarations = record['declarations']
            if not isinstance(declarations, dict) or len(declarations) > 16:
                raise ValueError('STYLE_CONTRACT_INVALID: invalid declarations')
            normalized, rejected = compile_declarations(';'.join(f'{k}:{v}' for k,v in declarations.items()))
            if rejected or normalized != declarations or record['className'] != class_for_style(declarations):
                raise ValueError('STYLE_CONTRACT_INVALID: forged or unsafe style rule')
            name = record['className']
            if name in rules and rules[name] != declarations:
                raise ValueError('STYLE_CONTRACT_INVALID: class collision')
            rules[name] = declarations
            local_classes.add(name)
            refs += 1
            if len(rules) > MAX_RULES_PER_PAGE:
                raise ValueError('STYLE_CONTRACT_INVALID: too many rules')
        if node.get('kind') == 'richText':
            html = (node.get('props') or {}).get('safeHtml', '')
            if not isinstance(html, str):
                raise ValueError('STYLE_CONTRACT_INVALID: invalid rich text')
            scanner = _ClassScanner()
            scanner.feed(html)
            if not scanner.classes.issubset(local_classes):
                raise ValueError('STYLE_CONTRACT_INVALID: styled HTML has an unmatched class')
    return dict(sorted(rules.items())), {'uniqueRules': len(rules), 'nodeRuleReferences': refs}


def compile_stylesheet(ir: dict, policy: str) -> tuple[str, dict]:
    if policy not in {'source-safe', 'target'}:
        raise ValueError('Unsupported source style policy')
    rules, summary = verified_rules(ir)
    kept = policy == 'source-safe'
    css = '/* Reviewed source formatting: deduplicated, no imports, URLs or scripting. */\n'
    if kept:
        css += ''.join(f':is(.rich-text,.target-body) .{name}'+'{'+';'.join(f'{prop}:{value}' for prop,value in props.items())+';}\n'
                       for name,props in rules.items())
    return css, {**summary, 'stylePolicy':policy, 'emittedRules': len(rules) if kept else 0,
                 'intentionallyOmittedRules': 0 if kept else len(rules),
                 'fidelity': 'unverified-no-computed-source-styles'}


def format_generated_css(raw: str) -> str:
    """Readable CSS for *compiler-owned* rules; preserves ordering and @media.

    This is not a user stylesheet sanitizer or a minifier. It never receives
    SharePoint CSS; unsupported compiler-owned constructs fail explicitly.
    """
    if tinycss2 is None:
        raise RuntimeError('CSS compiler requires tinycss2: pip install -r requirements.txt')
    if not isinstance(raw, str) or len(raw) > 200_000:
        raise ValueError('Generated CSS exceeds formatter limit')

    def render(rules, level=0):
        lines = []
        indent = '  ' * level
        for rule in rules:
            if rule.type == 'whitespace':
                continue
            if rule.type == 'comment':
                lines.append(indent + '/* ' + rule.value.strip().replace('*/','') + ' */')
                continue
            if rule.type == 'at-rule' and rule.content is not None and rule.lower_at_keyword in {'media', 'supports'}:
                title = tinycss2.serialize(rule.prelude).strip()
                lines.append(indent + '@' + rule.lower_at_keyword + ' ' + title + ' {')
                lines.extend(render(tinycss2.parse_rule_list(rule.content), level+1))
                lines.append(indent + '}')
                continue
            if rule.type != 'qualified-rule':
                raise ValueError('Unsupported generated CSS rule; do not guess formatting')
            selector = tinycss2.serialize(rule.prelude).strip()
            lines.append(indent + selector + ' {')
            for decl in tinycss2.parse_declaration_list(rule.content, skip_whitespace=True, skip_comments=True):
                if decl.type != 'declaration':
                    raise ValueError('Invalid compiler-owned CSS declaration')
                val = tinycss2.serialize(decl.value).strip()
                important = ' !important' if decl.important else ''
                lines.append(indent + '  ' + decl.name + ': ' + val + important + ';')
            lines.append(indent + '}')
        return lines
    return '\n'.join(render(tinycss2.parse_stylesheet(raw))) + '\n'


class SourceCodeAudit(HTMLParser):
    """Count untrusted script/style dependencies without storing code or URLs."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.counts: Counter[str] = Counter()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'script':
            self.counts['externalScripts' if attributes.get('src') else 'inlineScripts'] += 1
        if tag == 'style':
            self.counts['embeddedStylesheets'] += 1
        if tag == 'link' and str(attributes.get('rel') or '').lower() == 'stylesheet':
            self.counts['linkedStylesheets'] += 1
        for key,_ in attrs:
            if key.lower().startswith('on'):
                self.counts['inlineEventHandlers'] += 1
        if tag in {'iframe', 'object', 'embed'}:
            self.counts['unsupportedEmbeds'] += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def audit_source_code(raw: str) -> dict[str,int]:
    if not isinstance(raw, str) or len(raw) > 1_000_000:
        raise ValueError('Source HTML too large for script/style audit')
    parser = SourceCodeAudit()
    parser.feed(raw)
    parser.close()
    return dict(sorted(parser.counts.items()))


def presentation_report(ir: dict, style_summary: dict) -> dict:
    source = Counter()
    findings = []
    for node in _walk(ir['tree']):
        audit = (node.get('props') or {}).get('sourceCodeAudit') or {}
        if audit:
            source.update(audit)
            findings.append({'nodeId':node['id'],'counts':audit})
    behavior = sum(source.get(key,0) for key in ('externalScripts','inlineScripts','inlineEventHandlers','unsupportedEmbeds'))
    return {'compilerVersion':'presentation-0.1', 'stylesheet':style_summary,
            'sourceCodeInventory':dict(sorted(source.items())), 'perNode':findings,
            'behavior':{'status':'review-required' if behavior else 'no-source-scripts-detected',
                        'executableSourceScriptsCopied':0,
                        'note':'Untrusted scripts are not executed or compiled; behavior must be remapped and tested.'},
            'scope':'Rich-text HTML attributes and tags only; SPFx bundles, linked stylesheet fetches, and computed CSS are not yet analyzed'}


def _walk(node):
    yield node
    for child in node.get('children',[]):
        yield from _walk(child)
