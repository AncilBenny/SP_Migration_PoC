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
    args = parser.parse_args()
    if args.command == 'build':
        result = build(args.input, args.out, Path(__file__).parent / 'assets', style_mode=args.style_mode)
    elif args.command == 'map':
        result = build_target(args.ir, args.profile, args.out, strict=args.strict)
    else:
        from .validation import validate_target_file
        result = validate_target_file(args.ir, args.html, args.profile)
    print(json.dumps(result, indent=2))
    if args.command == 'validate' and not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
