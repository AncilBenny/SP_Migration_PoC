"""Modern SharePoint sample -> CIR -> target preview + portable ZIP.

The interface is deliberately separated from parsing/normalization: the target
renderer reads only generic CIR data. No network access or tenant credentials.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from html import escape
from io import BytesIO
import json
from pathlib import Path
import secrets
from threading import RLock
from zipfile import ZIP_DEFLATED, ZipFile

from poc.canvas import decode_modern_canvas
from poc.engine import STRUCTURAL_CSS, normalize, render_node
from poc.mapping import render_target, validate_profile
from poc.validation import ir_to_html, source_to_ir
from .quality import release_decision

ROOT = Path(__file__).resolve().parents[1]
MAX_PROJECTS = 12
SAMPLES = {
    'modern-demo': ('Modern overview', 'Graph-shaped public documentation adaptation', 'poc/samples/modern-demo.json'),
    'modern-internal-links': ('Internal links', 'Graph-shaped demo with destination URL rewrites', 'poc/samples/modern-internal-links.json'),
    'pnp-public-canvas': ('Public PnP canvas', 'MIT-licensed public CanvasContent1 fixture; custom web part', 'poc/samples/pnp-canvas-public.json'),
    'cdph-root-routing-demo': ('Separate URL roots', 'Synthetic page, image and document paths for routing demo; not a CDPH export', 'poc/samples/modern-cdph-routes-demo.json'),
    'modern-rich-layout': ('Rich Modern layout', 'Public Microsoft Graph API contracts adapted: title image, 8/4 grid, vertical section', 'poc/samples/modern-rich-layout-public-adapted.json'),
    'modern-style-compiler': ('Styles & scripts cleanup', 'Synthetic Graph-shaped sample: safe CSS classes, blocked scripts and event handlers', 'poc/samples/modern-styles-scripts-demo.json'),
    'modern-interactions': ('Accessible behaviors', 'Synthetic rich-text headings for explicitly reviewed accordion and tab mappings', 'poc/samples/modern-interactions-synthetic.json'),
}


def list_samples() -> list[dict]:
    return [{'id': key, 'title': title, 'description': description} for key, (title, description, _) in SAMPLES.items()]


def _sample_source(sample_id: str) -> dict:
    if sample_id not in SAMPLES:
        raise ValueError('Unknown public sample')
    return json.loads((ROOT / SAMPLES[sample_id][2]).read_text(encoding='utf-8'))


def _check_source_limits(document: object) -> None:
    """Defend the local parser against pathologically deep or huge JSON trees."""
    stack = [(document, 0)]
    visited = 0
    while stack:
        value, depth = stack.pop()
        visited += 1
        if visited > 50_000 or depth > 48:
            raise ValueError('Source page exceeds the safe structural complexity limit')
        if isinstance(value, dict):
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)


def _capture(source: dict, *, trusted_sample: bool) -> tuple[dict, dict, list[dict]]:
    if not isinstance(source, dict):
        raise ValueError('The imported page must be a JSON object')
    _check_source_limits(source)
    if isinstance((source.get('ListItemAllFields') or {}).get('CanvasContent1'), str):
        graph, findings = decode_modern_canvas(source)
    else:
        graph, findings = source, []
    asset_map = source.get('_assetMap', {}) if trusted_sample else {}
    if trusted_sample and asset_map:
        if asset_map != {'https://example.org/sites/demo/SiteAssets/health.svg': 'assets/health.svg'}:
            raise ValueError('Public sample has an unexpected asset mapping')
    ir = normalize(graph, asset_map=asset_map)
    # Source-adapter diagnostics are retained and visible to reviewers.
    ir['diagnostics'].extend(findings)
    return graph, ir, findings


def _walk(node: dict):
    yield node
    for child in node.get('children', []):
        yield from _walk(child)


@dataclass
class Project:
    id: str
    label: str
    graph: dict
    ir: dict
    source_check: dict
    sample_id: str | None
    trusted_sample: bool
    outputs: dict[str, 'Output'] = field(default_factory=dict)


@dataclass
class Output:
    files: dict[str, bytes]
    report: dict
    quality: dict


class ProjectStore:
    """Ephemeral local workflow state; process restart clears all imports."""
    def __init__(self):
        self._projects: dict[str, Project] = {}
        self._lock = RLock()

    def analyze(self, *, sample_id: str | None = None, source: dict | None = None) -> dict:
        if (sample_id is None) == (source is None):
            raise ValueError('Provide either a public sample or an imported source, not both')
        trusted_sample = sample_id is not None
        document = _sample_source(sample_id) if trusted_sample else source
        graph, ir, _ = _capture(document, trusted_sample=trusted_sample)
        check = source_to_ir(graph, ir)
        project_id = secrets.token_urlsafe(15)
        label = SAMPLES[sample_id][0] if trusted_sample else str(graph.get('title') or 'Imported Modern page')[:120]
        project = Project(project_id, label, graph, ir, check, sample_id, trusted_sample)
        with self._lock:
            if len(self._projects) >= MAX_PROJECTS:
                self._projects.pop(next(iter(self._projects)))
            self._projects[project_id] = project
        nodes = list(_walk(ir['tree']))
        return {
            'projectId': project_id,
            'label': label,
            'sourceType': 'modern-sharepoint-public-fixture' if trusted_sample else 'modern-sharepoint-uploaded-json',
            'sourceCheck': check,
            'ir': ir,
            'inventory': dict(Counter(node['kind'] for node in nodes)),
            'nodeCount': len(nodes),
            'warningCount': len(ir.get('diagnostics', [])),
            'provenance': 'public fixture / adapted documentation; not a live-tenant export' if trusted_sample else 'user-supplied local JSON, unverified origin'
        }

    def _project(self, project_id: str) -> Project:
        with self._lock:
            project = self._projects.get(project_id)
        if not project:
            raise KeyError('Project not found; re-import the source page')
        return project

    def render(self, project_id: str, *, mode: str = 'client', profile: dict | None = None) -> dict:
        project = self._project(project_id)
        from poc.contracts import validate_ir
        validate_ir(project.ir)
        if mode not in {'client', 'structural'}:
            raise ValueError('Unknown destination mode')
        if mode == 'client':
            if profile is None:
                profile = json.loads((ROOT / 'poc/profiles/client-example.json').read_text(encoding='utf-8'))
            validate_profile(profile)
            html, css, report = render_target(project.ir, profile)
            validation_profile = profile
        else:
            if profile is not None:
                raise ValueError('Structural output does not use a destination profile')
            ir_page = project.ir['page']
            title = escape(ir_page.get('title', 'Untitled'))
            description = escape(ir_page.get('description', ''), quote=True)
            body = render_node(project.ir['tree'])
            html = (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
                    f'<meta name="viewport" content="width=device-width,initial-scale=1">'
                    f'<meta name="description" content="{description}"><title>{title}</title>'
                    f'<link rel="stylesheet" href="style.css"></head><body><main>{body}</main></body></html>')
            from poc.style_compiler import compile_stylesheet, presentation_report
            _, style_summary = compile_stylesheet(project.ir, 'source-safe')
            report = {'profileId': None, 'targetFormat': 'html-css', 'mappedComponents': {}, 'mappingWarnings': [],
                      'presentation':presentation_report(project.ir, style_summary)}
            from poc.style_compiler import format_generated_css
            css = format_generated_css(STRUCTURAL_CSS)
            if style_summary['emittedRules']:
                html = html.replace('</head>', '<link rel="stylesheet" href="source-styles.css"></head>')
            validation_profile = {'id': 'structural', 'version': '1.0', 'assetDirectory': 'assets'}
        from poc.style_compiler import compile_stylesheet
        if report['presentation']['stylesheet']['emittedRules']:
            source_css, _ = compile_stylesheet(project.ir, 'source-safe')
        files: dict[str, bytes] = {
            'index.html': html.encode('utf-8'),
            'style.css': css.encode('utf-8'),
            'page.ir.json': (json.dumps(project.ir, indent=2) + '\n').encode('utf-8'),
        }
        if mode == 'client' and report.get('behavior', {}).get('scriptAssets'):
            from poc.behavior_compiler import BEHAVIOR_JS
            files['behavior.js'] = BEHAVIOR_JS.encode('utf-8')
        files['presentation-report.json'] = (json.dumps(report['presentation'], indent=2) + '\n').encode('utf-8')
        from poc.behavior_evidence import compare_destination_behavior
        behavior_evidence = (report.get('behaviorEvidence') if mode == 'client' else
                             compare_destination_behavior(project.ir, html, {}, {}))
        files['behavior-evidence.json'] = (json.dumps(behavior_evidence, indent=2) + '\n').encode('utf-8')
        if report['presentation']['stylesheet']['emittedRules']:
            files['source-styles.css'] = source_css.encode('utf-8')
        for asset in project.ir.get('assets', []):
            relative = asset.get('resolvedUrl', '')
            if relative == 'assets/health.svg' and project.trusted_sample:
                folder = profile.get('assetDirectory', 'assets') if mode == 'client' else 'assets'
                files[f'{folder}/health.svg'] = (ROOT / 'poc/assets/health.svg').read_bytes()
        output_check = ir_to_html(project.ir, html, validation_profile)
        # Check the expected local assets also exist in the export.
        missing = []
        files['presentation-report.json'] = (json.dumps(report['presentation'], indent=2) + '\n').encode('utf-8')
        if report['presentation']['stylesheet']['emittedRules']:
            files['source-styles.css'] = source_css.encode('utf-8')
        for asset in project.ir.get('assets', []):
            p = asset.get('resolvedUrl', '')
            if p.startswith('assets/'):
                target_folder = validation_profile.get('assetDirectory', 'assets')
                target_path = target_folder + '/' + p[len('assets/'):]
                if target_path not in files:
                    missing.append(target_path)
        if missing:
            output_check['passed'] = False
            output_check.setdefault('items', []).extend({'nodeId': path, 'kind': 'asset', 'status': 'lost', 'reason': 'Local bundled asset unavailable'} for path in missing)
            output_check['summary']['lost'] = output_check['summary'].get('lost', 0) + len(missing)
        from poc.dependencies import audit_export
        from poc.acquisition import plan_acquisition
        acquisition_plan = plan_acquisition(project.ir, validation_profile)
        files['acquisition-plan.json'] = (json.dumps(acquisition_plan, indent=2) + '\n').encode('utf-8')
        dependency_audit = audit_export(project.ir, html, files, mode=mode)
        # Do not publish temporary Graph/SharePoint bearer-style links in an
        # export, even if content mapping otherwise succeeded.
        if dependency_audit['sourceSensitiveReferenceCount'] or any(d['status'] == 'blocked' and d['reason'].startswith('Preauthenticated')
               for d in dependency_audit['dependencies']):
            raise ValueError('PREAUTHENTICATED_REFERENCE_BLOCKED: remove temporary credential URLs before export')
        if dependency_audit['blocked']:
            output_check['passed'] = False
            output_check.setdefault('items', []).append({
                'nodeId': 'dependency-manifest', 'kind': 'dependency', 'status': 'lost',
                'reason': 'Missing or unsafe dependencies in the exported page'})
            output_check['summary']['lost'] = output_check['summary'].get('lost', 0) + 1
        decision = release_decision(project.source_check, output_check, project.ir.get('diagnostics', []))
        quality = {
            'releaseDecision': decision, 'dependencyAudit': dependency_audit['summary'], 'acquisitionCandidates': acquisition_plan['count'],
            'version': 'mvp-0.1', 'sourceToIr': project.source_check, 'irToHtml': output_check,
            'passed': project.source_check['passed'] and output_check['passed'],
            'visualFidelity': 'unverified-no-matched-source-screenshot',
            'presentation': report['presentation'],
            'behavior': report.get('behavior', {'compiled':[], 'sourceRuntimeCopied':False}),
            'behaviorEvidence': behavior_evidence,
            'scope': 'Content, assets, safe authored CSS declarations, script inventory, explicit destination behavior mappings; no computed CSS or source-vs-target interaction comparison',
        }
        files['dependency-manifest.json'] = (json.dumps(dependency_audit, indent=2) + '\n').encode('utf-8')
        files['quality-report.json'] = (json.dumps(quality, indent=2) + '\n').encode('utf-8')
        if mode == 'client':
            files['mapping-report.json'] = (json.dumps(report, indent=2) + '\n').encode('utf-8')
        files['manifest.json'] = (json.dumps({
            'generator': 'Migration Studio MVP 0.1', 'mode': mode,
            'source': 'Modern SharePoint public fixture / imported JSON',
            'visualFidelity': quality['visualFidelity'], 'files': sorted(files),
        }, indent=2) + '\n').encode('utf-8')
        project.outputs[mode] = Output(files, report, quality)
        return {
            'projectId': project_id, 'mode': mode, 'quality': quality,
            'mappingReport': report, 'previewUrl': f'/api/preview/{project_id}/{mode}/index.html',
            'exportUrl': f'/api/export/{project_id}/{mode}',
            'files': sorted(files),
        }

    def review_stylesheet(self, project_id: str, mode: str, source_css: str, selector_map: dict | None = None) -> dict:
        """Analyze supplied CSS against a generated page, without applying it.

        Keep a separate review artifact in the export, never change the CIR or
        automatically inject reviewed candidate CSS into the destination.
        """
        if mode not in {'client', 'structural'}:
            raise ValueError('Unknown output mode')
        project = self._project(project_id)
        output = project.outputs.get(mode)
        if output is None:
            raise ValueError('Generate a destination before reviewing a stylesheet')
        from poc.css_workbench import compile_reviewed_css
        css, report = compile_reviewed_css(source_css, output.files['index.html'].decode('utf-8'), selector_map=selector_map)
        output.files['reviewed-candidates.css'] = css.encode('utf-8')
        output.files['css-review.json'] = (json.dumps(report, indent=2) + '\n').encode('utf-8')
        if selector_map is not None:
            from poc.css_workbench import validate_selector_map
            normalized = validate_selector_map(selector_map)
            # Reviewable artifact, never interpreted as a source CSS program.
            output.files['selector-mapping-review.json'] = (json.dumps({'version':'1.0', 'mappings':[{'sourceSelector':k, 'targetComponent':v} for k,v in sorted(normalized.items())]}, indent=2) + '\n').encode('utf-8')
        else:
            output.files.pop('selector-mapping-review.json', None)
        return {'report': report, 'css':css, 'applied':False,
                'note':'Review-only. No source CSS is automatically applied to the migrated page.'}

    def review_visual(self, project_id: str, mode: str, source_png: bytes, viewport_width: int, *, target_screenshot: bytes | None = None) -> dict:
        """Compare a reviewer-supplied source PNG to a network-isolated target capture.

        Never exports the original screenshot or derived pixel heatmap. Only the
        numerical report is stored in this project's local export.
        The optional injected target is for tests; the HTTP API never accepts it.
        """
        if mode not in {'client', 'structural'}:
            raise ValueError('Unknown output mode')
        project = self._project(project_id)
        output = project.outputs.get(mode)
        if output is None:
            raise ValueError('Generate a destination before visual review')
        if viewport_width not in (390, 1440) or type(viewport_width) is not int:
            raise ValueError('VISUAL_VIEWPORT_INVALID: Studio supports 390 or 1440')
        # Validate the source screenshot before invoking an expensive browser.
        from poc.visual_compare import _decode_png
        baseline=_decode_png(source_png)
        if baseline.width != viewport_width:
            raise ValueError('VISUAL_VIEWPORT_MISMATCH: source PNG width must equal the declared viewport')
        if target_screenshot is None:
            from tempfile import TemporaryDirectory
            from pathlib import Path, PurePosixPath
            from poc.browser_audit import audit_browser_page
            with TemporaryDirectory(prefix='migration-visual-') as scratch:
                workspace = Path(scratch)
                for name, data in output.files.items():
                    path = PurePosixPath(name)
                    if path.is_absolute() or '..' in path.parts or not path.parts or not isinstance(data, bytes):
                        raise ValueError('VISUAL_TARGET_INVALID: non-portable generated file')
                    destination=workspace.joinpath(*path.parts)
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    destination.write_bytes(data)
                review_dir=workspace/'browser-review'
                browser_report=audit_browser_page(workspace/'index.html',review_dir)
                label='mobile' if viewport_width==390 else 'desktop'
                target_screenshot=(review_dir/(label+'.png')).read_bytes()
                structural_passed=browser_report['structuralPassed']
                component_geometry=browser_report['viewports'][label]['componentGeometry']
        else:
            structural_passed=None
            component_geometry=None
        from poc.visual_compare import compare_screenshots
        report,heatmap=compare_screenshots(source_png,target_screenshot,viewport_width=viewport_width,include_heatmap=True,
                                            components=component_geometry,
                                            node_mappings=output.report.get('nodeMappings',[]) if component_geometry is not None else None)
        report['destinationCapture']='offline-static-chromium-js-disabled-network-blocked' if structural_passed is not None else 'test-injected-target-png'
        report['destinationStructuralPassed']=structural_passed
        report['baselineProvenance']='reviewer-asserted-unverified'
        report['componentAttribution']='overlap-only-not-root-cause' if component_geometry is not None else 'unavailable-no-target-dom-geometry'
        report['componentGeometrySource']='matching-offline-chromium-capture' if component_geometry is not None else 'not-captured' 
        report['reviewRequired']=True
        report['releaseApproved']=False
        # Do not bundle uploaded originals, generated screenshot or heatmap.
        output.files['visual-review.json']=(json.dumps(report,indent=2)+'\n').encode('utf-8')
        manifest=json.loads(output.files['manifest.json'])
        manifest['files']=sorted(output.files)
        output.files['manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode('utf-8')
        import base64
        return {'report':report,'heatmapDataUrl':'data:image/png;base64,'+base64.b64encode(heatmap).decode('ascii'),
                'exportedArtifacts':['visual-review.json'], 'sourceScreenshotExported':False,
                'note':'Comparison is review-only: user-supplied baseline and no authenticated SharePoint source render.'}

    def output_file(self, project_id: str, mode: str, file_path: str) -> bytes:
        project = self._project(project_id)
        result = project.outputs.get(mode)
        if result is None or file_path not in result.files:
            raise KeyError('Output file unavailable; generate preview first')
        return result.files[file_path]

    def export(self, project_id: str, mode: str) -> bytes:
        project = self._project(project_id)
        result = project.outputs.get(mode)
        if result is None:
            raise KeyError('Output unavailable; generate it before export')
        content = BytesIO()
        with ZipFile(content, 'w', ZIP_DEFLATED) as archive:
            for name, body in result.files.items():
                archive.writestr(name, body)
        return content.getvalue()
