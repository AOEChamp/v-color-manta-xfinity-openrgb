"""Rebuild patched v1 from the bundled, hash-guarded stock image."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / '_internal'))
from firmware_image import build, SOURCE, OUTPUT


def main():
    image, manifest = build(SOURCE.read_bytes())
    OUTPUT.write_bytes(image)
    OUTPUT.with_suffix('.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Built: {OUTPUT}')
    print(f"SHA-256: {manifest['candidate_sha256']}")


if __name__ == '__main__':
    main()
