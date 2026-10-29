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
    'modern-rich-layout': ('Rich Modern layout', 'Public Microsoft Graph API contracts adapted: title image, 8/4 grid, vertical section', 'poc/samples/modern-rich-layout-public-adapted.json'),
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
            css, report = STRUCTURAL_CSS, {'profileId': None, 'targetFormat': 'html-css', 'mappedComponents': {}, 'mappingWarnings': []}
            validation_profile = {'id': 'structural', 'version': '1.0', 'assetDirectory': 'assets'}
        files: dict[str, bytes] = {
            'index.html': html.encode('utf-8'),
            'style.css': css.encode('utf-8'),
            'page.ir.json': (json.dumps(project.ir, indent=2) + '\n').encode('utf-8'),
        }
        for asset in project.ir.get('assets', []):
            relative = asset.get('resolvedUrl', '')
            if relative == 'assets/health.svg' and project.trusted_sample:
                folder = profile.get('assetDirectory', 'assets') if mode == 'client' else 'assets'
                files[f'{folder}/health.svg'] = (ROOT / 'poc/assets/health.svg').read_bytes()
        output_check = ir_to_html(project.ir, html, validation_profile)
        # Check the expected local assets also exist in the export.
        missing = []
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
        decision = release_decision(project.source_check, output_check, project.ir.get('diagnostics', []))
        quality = {
            'releaseDecision': decision,
            'version': 'mvp-0.1', 'sourceToIr': project.source_check, 'irToHtml': output_check,
            'passed': project.source_check['passed'] and output_check['passed'],
            'visualFidelity': 'unverified-no-matched-source-screenshot',
            'scope': 'Content/structure and link/asset checks for supported controls; no computed CSS or JS comparison',
        }
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
