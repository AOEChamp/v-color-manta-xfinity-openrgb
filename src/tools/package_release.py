"""Populate bin with the runtime and files needed by end users. No archives."""
from pathlib import Path
import shutil
import argparse

ROOT = Path(__file__).resolve().parents[2]
WINDOWS_FILES = ('Bridge.ps1', 'Install.cmd', 'Uninstall.cmd', 'Start.cmd', 'Stop.cmd',
                 'README.txt', 'bridge-config.example.json')


def package(root=ROOT, runtime=None):
    root = Path(root)
    runtime = Path(runtime) if runtime else root / 'build/runtime/VColorOpenRGBBridge'
    if not (runtime / 'VColorOpenRGBBridge.exe').is_file() or not (runtime / '_internal').is_dir():
        raise RuntimeError('Build the executable and bundled runtime before packaging')
    entries = [(root / 'src/windows' / name, Path(name)) for name in WINDOWS_FILES]
    entries += [(root / name, Path(name)) for name in ('LICENSE','THIRD_PARTY_NOTICES.md')]
    entries += [(root / 'src/licenses' / name, Path(name))
                for name in ('PYTHON-LICENSE.txt','PYINSTALLER-COPYING.txt')]
    entries += [(p, p.relative_to(runtime)) for p in sorted(runtime.rglob('*')) if p.is_file()]
    output = root / 'bin'
    for source, relative in entries:
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    print(f'{output}: {len(entries)} end-user files; no archive created')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir')
    package(runtime=parser.parse_args().runtime_dir)
