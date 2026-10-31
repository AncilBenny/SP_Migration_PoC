"""Evidence-based interaction discovery and static destination contract comparison.

No arbitrary source script execution or behavior inference. Structural candidates
are merely authoring opportunities, not evidence of the original site's behavior.
The validator checks generated HTML, not the mapping report's own claims.
"""
from __future__ import annotations

from collections import Counter
from html.parser import HTMLParser
from typing import Any

SCRIPT_KEYS = ('externalScripts', 'inlineScripts', 'inlineEventHandlers', 'unsupportedEmbeds')
SCRIPT_REQUIRED = frozenset({'tabs', 'filterLinks'})
_SUPPORTED = frozenset({'accordion', 'tabs', 'toc', 'filterLinks'})
_VOID = frozenset({'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'})


def _walk(node: dict):
    yield node
    for child in node.get('children', []):
        yield from _walk(child)


class _HeadingProbe(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.levels = Counter()
    def handle_starttag(self, tag, attrs):
        if tag in ('h2', 'h3'):
            self.levels[tag] += 1


class _OutputProbe(HTMLParser):
    """Associate compiler wrappers with descendants' data-ir-id markers.

    The existing compiler deliberately nests data-ir-id *within* interactive
    wrappers for navigation/filtering, so the audit must not assume a marker is
    their parent. It instead tracks a single generated behavior subtree.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.contexts: list[str|None] = []
        self.active: list[dict] = []
        self.by_node: dict[str, Counter] = {}
        self.script_src: list[str] = []
        self.malformed = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        context = a.get('data-ir-id') or (self.contexts[-1] if self.contexts else None)
        kind = a.get('data-behavior')
        if kind in _SUPPORTED:
            self.active.append({'kind':kind,'depth':len(self.stack),
                                'counts':Counter({'root:' + kind:1}), 'nodes':set()})
        for block in self.active:
            if context:
                block['nodes'].add(context)
            count = block['counts']
            if tag == 'details': count['details'] += 1
            if tag == 'summary': count['summary'] += 1
            if 'mig-tab-panel' in (a.get('class') or '').split(): count['tabPanels'] += 1
            if a.get('role') == 'tablist': count['tablist'] += 1
            if tag == 'a' and (a.get('href') or '').startswith('#mig-section-'): count['tocLinks'] += 1
            if 'mig-toc-section' in (a.get('class') or '').split(): count['tocSections'] += 1
            if 'data-filter-item' in a: count['filterItems'] += 1
            if tag == 'input' and a.get('type') == 'search': count['searchInputs'] += 1
            if 'mig-filter-status' in (a.get('class') or '').split(): count['filterStatus'] += 1
        if tag == 'script': self.script_src.append(a.get('src') or '')
        if tag not in _VOID:
            self.stack.append(tag)
            self.contexts.append(context)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID: self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.malformed = True
            return
        self.stack.pop()
        self.contexts.pop()
        while self.active and len(self.stack) == self.active[-1]['depth']:
            block = self.active.pop()
            for node_id in block['nodes']:
                self.by_node.setdefault(node_id, Counter()).update(block['counts'])



def discover_source_interactions(ir: dict) -> list[dict]:
    """Only authored facts and strictly labeled structural hypotheses."""
    findings = []
    for node in _walk(ir['tree']):
        node_id, kind = node['id'], node['kind']
        props = node.get('props') or {}
        source_ref = node.get('sourceRef')
        if kind == 'richText':
            inventory = props.get('sourceCodeAudit') or {}
            counts = {k:inventory[k] for k in SCRIPT_KEYS if isinstance(inventory.get(k), int) and inventory[k] > 0}
            if counts:
                findings.append({'nodeId': node_id, 'sourceRef':source_ref, 'category':'runtime-evidence',
                                 'status':'review-required', 'evidence':'source-fragment-inventory',
                                 'counts':counts, 'note':'Runtime found, but its purpose and behavior are unknown.'})
            headings = _HeadingProbe()
            headings.feed(str(props.get('safeHtml', '')))
            if max(headings.levels.values(),default=0) >= 2:
                findings.append({'nodeId':node_id,'sourceRef':source_ref,'category':'structural-candidate',
                                 'status':'not-source-behavior-evidence','evidence':'sanitized-headings',
                                 'headings':dict(headings.levels),
                                 'note':'May be suitable for a reviewed toc/tabs/accordion; NOT proof of original interaction.'})
        elif kind == 'linkList' and props.get('items'):
            findings.append({'nodeId':node_id,'sourceRef':source_ref,'category':'structural-candidate',
                             'status':'not-source-behavior-evidence','evidence':'link-list',
                             'linkCount':len(props['items']),
                             'note':'Links exist; filtering or search on the original page is unverified.'})
        elif kind == 'unknown':
            findings.append({'nodeId':node_id,'sourceRef':source_ref,'category':'unresolved-web-part',
                             'status':'review-required','evidence':'unsupported-control',
                             'note':'Unknown SPFx/control behavior cannot be reconstructed from this CIR.'})
    return findings


def compare_destination_behavior(ir: dict, html: str, profile: dict, mapping_report: dict|None = None) -> dict:
    """Compare source evidence, approved mapping and actual emitted HTML structures.

    This is NOT browser execution or matched SharePoint visual/behavior fidelity.
    """
    if len(html) > 3_000_000:
        raise ValueError('BEHAVIOR_AUDIT_TOO_LARGE')
    from .behavior_compiler import validate_behavior_mappings
    plan = validate_behavior_mappings(profile.get('behaviorMappings', []))
    probe = _OutputProbe();probe.feed(html);probe.close()
    compiled = {x['nodeId']:x for x in (mapping_report or {}).get('behavior', {}).get('compiled', [])}
    findings = discover_source_interactions(ir)
    checks=[]
    for node_id, config in plan.items():
        interaction=config['interaction']
        seen=probe.by_node.get(node_id, Counter())
        claimed=compiled.get(node_id)
        panels=(claimed.get('panels', claimed.get('items')) if claimed else None)
        errors=[]
        if not claimed or claimed.get('interaction') != interaction or not isinstance(panels,int) or panels < 2:
            errors.append('Missing or invalid compiled mapping record')
        if seen['root:' + interaction] != 1:
            errors.append('Expected exactly one compiled interaction root in this node')
        if panels and interaction=='accordion' and (seen['details'] != panels or seen['summary'] != panels):
            errors.append('Accordion panel/summary count mismatch')
        if panels and interaction=='tabs' and (seen['tabPanels'] != panels or seen['tablist'] != 1):
            errors.append('Tab panel/tablist count mismatch')
        if panels and interaction=='toc' and (seen['tocLinks'] != panels or seen['tocSections'] != panels):
            errors.append('On-page navigation section/link count mismatch')
        if panels and interaction=='filterLinks' and (seen['filterItems'] != panels or seen['searchInputs'] != 1 or seen['filterStatus'] != 1):
            errors.append('Filter item/search/status count mismatch')
        if interaction in SCRIPT_REQUIRED and probe.script_src.count('behavior.js') != 1:
            errors.append('Trusted behavior.js reference is absent or duplicated')
        checks.append({'nodeId':node_id,'interaction':interaction,'expectedItems':panels,
                       'status':'pass' if not errors else 'fail', 'issues':errors,
                       'sourceBehaviorVerified':False,'browserExecutionVerified':False})
    if probe.malformed or probe.stack or probe.active:
        checks.append({'nodeId':'__document__','status':'fail','issues':['Malformed generated HTML nesting']})
    failures=sum(x['status']=='fail' for x in checks)
    unresolved=sum(x['status']=='review-required' for x in findings)
    return {
      'version':'behavior-evidence-0.1',
      'sourceEvidence':findings,
      'destinationChecks':checks,
      'summary':{'sourceEvidenceItems':len(findings),'unresolvedSourceItems':unresolved,
                 'explicitMappings':len(plan),'staticChecksPassed':len(checks)-failures,
                 'staticChecksFailed':failures},
      'passed':failures==0,
      'sourceBehaviorFidelity':'unverified-no-observed-sharepoint-interaction-baseline',
      'destinationBrowserFidelity':'not-evaluated-static-html-only',
      'sourceScriptsCopied':False,
      'reviewRequired':True,
      'note':'Only target markup shape is checked. No proof of original SharePoint behavior or target browser execution.'
    }
