"""CLI: build original Modern source to CIR, or map an existing CIR to a target."""
import argparse
import json
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
    args = parser.parse_args()
    if args.command == 'build':
        result = build(args.input, args.out, Path(__file__).parent / 'assets', style_mode=args.style_mode)
    elif args.command == 'map':
        result = build_target(args.ir, args.profile, args.out, strict=args.strict)
    elif args.command == 'graph-plan':
        from .graph_assets import load_graph_metadata, resolve_graph_assets
        from .mapping import validate_profile
        profile = json.loads(args.profile.read_text(encoding='utf-8'))
        validate_profile(profile)
        raw = load_graph_metadata(args.drive_items)
        result = resolve_graph_assets(json.loads(args.ir.read_text(encoding='utf-8')), raw, profile)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
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
