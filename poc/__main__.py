"""CLI: python -m poc build --input poc/samples/modern-demo.json --out demo"""
import argparse
import json
from pathlib import Path
from .engine import build


def main():
    parser = argparse.ArgumentParser(description="Offline SharePoint modern page → CIR → HTML")
    parser.add_argument("command", choices=["build"])
    parser.add_argument("--input", type=Path, default=Path("poc/samples/modern-demo.json"))
    parser.add_argument("--out", type=Path, default=Path("demo"))
    parser.add_argument("--style-mode", choices=["structural", "demo"], default="structural", help="Default structural output avoids invented branding; demo uses illustrative styling")
    args = parser.parse_args()
    print(json.dumps(build(args.input, args.out, Path(__file__).parent / "assets", style_mode=args.style_mode), indent=2))


if __name__ == "__main__":
    main()
