"""Evidence-aware engine maturity and release gates for the local MVP.

A green supported-content check is NEVER an assertion of migration readiness.
No network, SharePoint dependency, or mutable global state.
"""
from __future__ import annotations

CAPABILITIES = [
    {'id': 'source-graph', 'name': 'Graph Modern sitePage intake', 'stage': 'source', 'maturity': 'prototype', 'supported': ['horizontal/vertical section content', '12-grid columns', 'title area image/flags', 'text', 'Image', 'Quick Links'], 'gaps': ['vertical section placement fidelity', 'custom SPFx', 'full title-area visuals', 'tenant authentication'], 'evidence': ['https://learn.microsoft.com/en-us/graph/api/sitepage-get?view=graph-rest-1.0']},
    {'id': 'source-canvas', 'name': 'PnP serialized CanvasContent1 decoder', 'stage': 'source', 'maturity': 'prototype', 'supported': ['published PnP encoded control fixture', 'unknown part accounting'], 'gaps': ['all encoded variants', 'custom script semantics', 'complete inline controls'], 'evidence': ['https://github.com/pnp/cli-microsoft365/blob/main/src/m365/spo/commands/page/page-get.mock.ts']},
    {'id': 'cir', 'name': 'Canonical page IR', 'stage': 'core', 'maturity': 'prototype', 'supported': ['semantic tree', 'layout fractions', 'source references', 'diagnostics'], 'gaps': ['production schema v1', 'full styles/behavior contract'], 'evidence': []},
    {'id': 'mapping', 'name': 'Client HTML/CSS mapping and rewrites', 'stage': 'target', 'maturity': 'prototype', 'supported': ['allow-listed components', 'profile tokens', 'URL/asset rewrites'], 'gaps': ['client registries', 'JS interaction mappings', 'real-world asset import'], 'evidence': []},
    {'id': 'validation', 'name': 'Content loss detection', 'stage': 'quality', 'maturity': 'prototype', 'supported': ['text', 'heading', 'links', 'images', 'unknown controls', 'fail-injection regression tests'], 'gaps': ['matched source visual baseline', 'responsive browser metrics', 'interaction testing'], 'evidence': ['https://learn.microsoft.com/en-us/sharepoint/dev/transform/modernize-userinterface-site-pages']},
    {'id': 'dependencies', 'name': 'Offline asset/link dependency audit', 'stage': 'quality', 'maturity': 'prototype', 'supported': ['HTML image/link discovery', 'local bundle SHA-256 checks', 'external URL review flags', 'signed URL refusal'], 'gaps': ['remote downloads', 'authenticated drive item resolution', 'CSS url/srcset dependencies', 'rights and malware scanning'], 'evidence': ['https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0']},
    {'id': 'visual-fidelity', 'name': 'Visual + behavior fidelity', 'stage': 'quality', 'maturity': 'not-verified', 'supported': [], 'gaps': ['source screenshot/CSS pairing', 'computed styles', 'interactive behaviors'], 'evidence': []},
]


def release_decision(source_check: dict, output_check: dict, diagnostics: list[dict]) -> dict:
    """Conservative evaluation: review is mandatory even when known checks pass."""
    reasons: list[str] = []
    if not source_check.get('passed') or not output_check.get('passed'):
        reasons.append('Supported content or asset preservation checks failed')
        status = 'blocked'
    else:
        status = 'review-required'
    needs_review = []
    for stage, check in [('source', source_check), ('output', output_check)]:
        for item in check.get('items', []):
            if item.get('status') in {'needs-review', 'lost'}:
                needs_review.append({'stage': stage, 'nodeId': item.get('nodeId'), 'status': item['status']})
    if needs_review:
        reasons.append(f'{len(needs_review)} control/accounting issues require review')
    if any(d.get('severity') == 'error' for d in diagnostics):
        if status != 'blocked':
            status = 'blocked'
        reasons.append('Source adapter reported an error-level diagnostic')
    reasons.append('Visual and interaction fidelity have not been verified against a matched source')
    return {
        'status': status,
        'readyForProduction': False,
        'passedSupportedChecks': bool(source_check.get('passed') and output_check.get('passed')),
        'reviewItems': needs_review,
        'reasons': reasons,
    }


def capabilities_snapshot() -> dict:
    return {'schemaVersion': 'mvp-0.1', 'scope': 'one Modern SharePoint source family',
            'productionReady': False, 'engineCapabilities': CAPABILITIES,
            'research': 'docs/mvp/01-engine-research-and-quality-gates.md',
            'validationPolicy': 'Supported-content pass is not a production-readiness claim.'}
