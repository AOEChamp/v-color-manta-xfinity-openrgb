"""Rebuild the final firmware from the bundled, hash-guarded stock image."""
import json
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / '_internal'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=('2', '3'), default='2')
    args = parser.parse_args()
    if args.version == '3':
        from firmware_v3 import build, SOURCE, OUTPUT
    else:
        from firmware_image import build, SOURCE, OUTPUT
    image, manifest = build(SOURCE.read_bytes())
    OUTPUT.write_bytes(image)
    OUTPUT.with_suffix('.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Built: {OUTPUT}')
    print(f"SHA-256: {manifest['candidate_sha256']}")


if __name__ == '__main__':
    main()
