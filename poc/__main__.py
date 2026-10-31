"""CLI: build original Modern source to CIR, or map an existing CIR to a target."""
import argparse
import json
import os
import re
from pathlib import Path
from .engine import build
from .mapping import build_target


def main():
    parser = argparse.ArgumentParser(description='Offline source cleanup + destination mapping')
    sub = parser.add_subparsers(dest='command', required=True)
    source = sub.add_parser('build', help='Modern Graph page JSON -> CIR + structural HTML/CSS')
    source.add_argument('--input', type=Path, default=Path('poc/samples/modern-demo.json'))
    source.add_argument('--out', type=Path, default=Path('demo'))
    source.add_argument('--style-mode', choices=['structural', 'demo'], default='structural')
    target = sub.add_parser('map', help='Generic CIR -> target-specific HTML/CSS (no SharePoint parsing)')
    target.add_argument('--ir', type=Path, required=True)
    target.add_argument('--profile', type=Path, default=Path('poc/profiles/client-example.json'))
    target.add_argument('--out', type=Path, default=Path('demo-client'))
    target.add_argument('--strict', action='store_true', help='Fail mapping if supported content is missing')
    check = sub.add_parser('validate', help='Audit generated HTML against its original CIR and target profile')
    check.add_argument('--ir', type=Path, required=True)
    check.add_argument('--html', type=Path, required=True)
    check.add_argument('--profile', type=Path, default=Path('poc/profiles/client-example.json'))
    pull = sub.add_parser('pull', help='Opt-in public HTTPS image/document acquisition (no SharePoint login)')
    pull.add_argument('--ir', type=Path, required=True)
    pull.add_argument('--profile', type=Path, default=Path('poc/profiles/client-example.json'))
    pull.add_argument('--out', type=Path, default=Path('pulled-assets'))
    pull.add_argument('--allow-host', action='append', default=[], help='Explicit allowed public source host (repeatable)')
    pull.add_argument('--plan-only', action='store_true', help='Create plan without network access')
    graph = sub.add_parser('graph-plan', help='Reconcile file references with offline Graph driveItem metadata')
    graph.add_argument('--ir', type=Path, required=True)
    graph.add_argument('--drive-items', type=Path, required=True, help='Graph driveItem list JSON; NO bearer tokens or signed URLs')
    graph.add_argument('--profile', type=Path, default=Path('poc/profiles/client-example.json'))
    graph.add_argument('--out', type=Path, default=Path('graph-acquisition-plan.json'))
    graph_check = sub.add_parser('graph-verify', help='Independently verify bytes staged by a Graph transport')
    graph_check.add_argument('--report', type=Path, required=True)
    graph_check.add_argument('--staged-root', type=Path, required=True)
    graph_stage = sub.add_parser('graph-stage', help='Opt-in authorized Graph staging via injected environment token')
    graph_stage.add_argument('--plan', type=Path, required=True)
    graph_stage.add_argument('--out', type=Path, required=True)
    graph_stage.add_argument('--allow-download-host', action='append', required=True,
                             help='Exact HTTPS redirect host (repeat for each approved CDN host)')
    graph_stage.add_argument('--auth-mode', choices=['env-token', 'entra-delegated'], default='env-token',
                             help='Explicit token provider: legacy env token or MSAL browser/PKCE')
    graph_stage.add_argument('--tenant-env', default='MIGRATION_ENTRA_TENANT_ID',
                             help='Environment variable containing tenant UUID, not a secret')
    graph_stage.add_argument('--client-env', default='MIGRATION_ENTRA_CLIENT_ID',
                             help='Environment variable containing registered public-client UUID')
    graph_stage.add_argument('--login-hint-env', default=None,
                             help='Optional local environment variable for account selection')
    graph_stage.add_argument('--scope', choices=['Files.Read', 'Sites.Selected', 'Files.SelectedOperations.Selected'],
                             default='Files.Read', help='Narrow delegated Graph read permission')
    graph_stage.add_argument('--silent-only', action='store_true',
                             help='Never launch an interactive browser login')
    graph_stage.add_argument('--token-env', default='MIGRATION_GRAPH_ACCESS_TOKEN',
                             help='Environment variable containing preauthorized Graph access token')
    auth_check = sub.add_parser('graph-auth-check', help='Offline Entra delegated-read configuration readiness (no login)')
    auth_check.add_argument('--tenant-env', default='MIGRATION_ENTRA_TENANT_ID')
    auth_check.add_argument('--client-env', default='MIGRATION_ENTRA_CLIENT_ID')
    auth_check.add_argument('--scope', choices=['Files.Read', 'Sites.Selected', 'Files.SelectedOperations.Selected'], default='Files.Read')
    graph_publish = sub.add_parser('graph-publish-local', help='Verify staging and copy to a local output package')
    graph_publish.add_argument('--report', type=Path, required=True)
    graph_publish.add_argument('--staged-root', type=Path, required=True)
    graph_publish.add_argument('--destination', type=Path, required=True)
    graph_publish.add_argument('--out', type=Path, default=Path('local-publication-report.json'))
    stylesheet = sub.add_parser('css-workbench', help='Offline review of source CSS into scoped safe candidates; never auto-apply')
    stylesheet.add_argument('--css', type=Path, required=True, help='A locally supplied CSS file; no imports fetched')
    stylesheet.add_argument('--html', type=Path, help='Generated index.html for observed semantic tags')
    stylesheet.add_argument('--out', type=Path, default=Path('css-review'))
    stylesheet.add_argument('--selector-map', type=Path, help='Reviewed JSON manifest of exact source selectors -> destination components')
    browser = sub.add_parser('browser-audit', help='Optional offline Chromium screenshots + responsive checks; no source baseline')
    browser.add_argument('--html', type=Path, required=True)
    browser.add_argument('--out', type=Path, default=Path('browser-review'))
    behavior = sub.add_parser('behavior-browser', help='Optional isolated browser check of generated destination interactions (no source parity)')
    behavior.add_argument('--ir', type=Path, required=True)
    behavior.add_argument('--html', type=Path, required=True)
    behavior.add_argument('--profile', type=Path, required=True)
    behavior.add_argument('--mapping-report', type=Path, required=True)
    behavior.add_argument('--out', type=Path, default=Path('behavior-browser-report.json'))
    visual = sub.add_parser('visual-compare', help='Offline source baseline vs generated screenshot: heatmap + review-only metrics')
    visual.add_argument('--source-png', required=True, type=Path, help='Authorized source screenshot captured by a reviewer')
    visual.add_argument('--target-png', required=True, type=Path, help='Generated screenshot from browser-audit desktop.png/mobile.png')
    visual.add_argument('--viewport-width', required=True, type=int, choices=[390, 768, 1024, 1440])
    visual.add_argument('--threshold', type=int, default=24, help='Max-channel pixel delta tolerance (0-100)')
    visual.add_argument('--out', type=Path, default=Path('visual-review'))
    visual.add_argument('--browser-report', type=Path, help='Optional matching browser-audit.json; screenshot SHA-256 checked')
    visual.add_argument('--mapping-report', type=Path, help='Optional client mapping-report.json for CIR component names')
    args = parser.parse_args()
    if args.command == 'build':
        result = build(args.input, args.out, Path(__file__).parent / 'assets', style_mode=args.style_mode)
    elif args.command == 'map':
        result = build_target(args.ir, args.profile, args.out, strict=args.strict)
    elif args.command == 'css-workbench':
        from .css_workbench import compile_reviewed_css
        css, result = compile_reviewed_css(args.css.read_text(encoding='utf-8'),
                                           args.html.read_text(encoding='utf-8') if args.html else '',
                                           selector_map=json.loads(args.selector_map.read_text(encoding='utf-8')) if args.selector_map else None)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'reviewed-candidates.css').write_text(css, encoding='utf-8')
        (args.out / 'css-review.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    elif args.command == 'behavior-browser':
        from .behavior_browser import audit_behavior_browser_files
        result = audit_behavior_browser_files(args.ir, args.html, args.profile, args.mapping_report, args.out)
        if not result['passed']:
            raise SystemExit('BEHAVIOR_BROWSER_AUDIT_FAILED: see output report')
    elif args.command == 'visual-compare':
        from .visual_compare import compare_screenshot_files
        result = compare_screenshot_files(args.source_png, args.target_png, args.out, viewport_width=args.viewport_width, threshold=args.threshold, browser_report=args.browser_report, mapping_report=args.mapping_report)
    elif args.command == 'browser-audit':
        from .browser_audit import audit_browser_page
        result = audit_browser_page(args.html, args.out)
    elif args.command == 'graph-plan':
        from .graph_assets import load_graph_metadata, resolve_graph_assets
        from .mapping import validate_profile
        profile = json.loads(args.profile.read_text(encoding='utf-8'))
        validate_profile(profile)
        raw = load_graph_metadata(args.drive_items)
        result = resolve_graph_assets(json.loads(args.ir.read_text(encoding='utf-8')), raw, profile)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    elif args.command == 'graph-auth-check':
        from .entra_auth import DelegatedAuthConfig, EntraAuthError
        if not all(re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', name) for name in (args.tenant_env, args.client_env)):
            raise SystemExit('ENTRA_INVALID_ENV_NAME')
        try:
            result = DelegatedAuthConfig(tenant_id=os.environ.get(args.tenant_env, ''),
                                         client_id=os.environ.get(args.client_env, ''),
                                         scope=args.scope).readiness()
        except EntraAuthError as e:
            raise SystemExit(str(e)) from None
    elif args.command == 'graph-stage':
        from .graph_assets import stage_graph_files
        from .graph_transport import GraphBinaryFetcher
        if args.auth_mode == 'entra-delegated':
            from .entra_auth import DelegatedAuthConfig, EntraDelegatedTokenProvider, EntraAuthError
            env_names = [args.tenant_env, args.client_env]
            if args.login_hint_env is not None:
                env_names.append(args.login_hint_env)
            if not all(re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', name) for name in env_names):
                raise SystemExit('ENTRA_INVALID_ENV_NAME')
            try:
                config = DelegatedAuthConfig(
                    tenant_id=os.environ.get(args.tenant_env, ''),
                    client_id=os.environ.get(args.client_env, ''),
                    scope=args.scope, allow_interactive=not args.silent_only,
                    login_hint=os.environ.get(args.login_hint_env) if args.login_hint_env else None)
                token_provider = EntraDelegatedTokenProvider(config)
            except EntraAuthError as e:
                raise SystemExit(str(e)) from None
        else:
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', args.token_env):
                raise SystemExit('Invalid token environment variable name')
            if not os.environ.get(args.token_env):
                raise SystemExit('Graph access token environment variable is not set')
            token_provider = lambda: os.environ.get(args.token_env, '')
        fetcher = GraphBinaryFetcher(token_provider, redirect_hosts=set(args.allow_download_host))
        plan = json.loads(args.plan.read_text(encoding='utf-8'))
        result = stage_graph_files(plan, args.out, fetcher=fetcher)
    elif args.command == 'graph-publish-local':
        from .publication import LocalDirectoryStore, publish_staged_assets
        report = json.loads(args.report.read_text(encoding='utf-8'))
        result = publish_staged_assets(report, args.staged_root,
                                       LocalDirectoryStore(args.destination), output_report=args.out)
    elif args.command == 'graph-verify':
        from .graph_assets import verify_graph_staging
        result = verify_graph_staging(json.loads(args.report.read_text(encoding='utf-8')), args.staged_root)
    elif args.command == 'validate':
        from .validation import validate_target_file
        result = validate_target_file(args.ir, args.html, args.profile)
    else:
        from .acquisition import plan_acquisition, pull_public_files
        from .mapping import validate_profile
        profile = json.loads(args.profile.read_text(encoding='utf-8'))
        validate_profile(profile)
        plan = plan_acquisition(json.loads(args.ir.read_text(encoding='utf-8')), profile)
        if args.plan_only:
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / 'acquisition-plan.json').write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
            result = plan
        else:
            result = pull_public_files(plan, args.out, set(args.allow_host))
    print(json.dumps(result, indent=2))
    if args.command in ('validate', 'graph-verify') and not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
