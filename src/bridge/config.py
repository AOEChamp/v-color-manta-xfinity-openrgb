"""Validated configuration and portable OpenRGB discovery (no hardware access).
SPDX-License-Identifier: GPL-2.0-or-later
"""
import json
import os
from pathlib import Path
import shutil
import sys

VERSION = '0.4.0'
DEFAULTS = {
    'openrgb_dir': None,
    'port': 6743,
    'smbus_port': 0,
}


def package_root():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def load_config(path=None):
    explicit = path is not None
    path = Path(path) if path else package_root() / 'bridge-config.json'
    settings = dict(DEFAULTS)
    if path.exists():
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict):
            raise ValueError('Configuration must be a JSON object')
        unknown = data.keys() - DEFAULTS.keys()
        if unknown:
            raise ValueError('Unknown configuration keys: ' + ', '.join(sorted(unknown)))
        settings.update(data)
    elif explicit:
        raise ValueError(f'Configuration not found: {path}')
    if settings['openrgb_dir'] is not None and not isinstance(settings['openrgb_dir'], str):
        raise ValueError('openrgb_dir must be a directory string or null')
    if type(settings['port']) is not int or not 1024 <= settings['port'] <= 65535:
        raise ValueError('port must be an integer from 1024 to 65535')
    if type(settings['smbus_port']) is not int or settings['smbus_port'] not in (0, 1):
        raise ValueError('smbus_port must be 0 or 1 (AMD PIIX4)')
    if settings['openrgb_dir']:
        folder = Path(os.path.expandvars(settings['openrgb_dir'])).expanduser()
        if not folder.is_absolute():
            folder = path.resolve().parent / folder
        settings['openrgb_dir'] = str(folder.resolve())
    return settings


def find_openrgb(explicit=None, root=None):
    root = Path(root) if root else package_root()
    candidates = [Path(explicit)] if explicit else [root / 'OpenRGB', root]
    if not explicit:
        for key in ('ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)'):
            if os.environ.get(key):
                candidates.append(Path(os.environ[key]) / 'OpenRGB')
        executable = shutil.which('OpenRGB.exe')
        if executable:
            candidates.append(Path(executable).parent)
    required = ('OpenRGB.exe', 'PawnIOLib.dll', 'SmbusPIIX4.bin')
    for candidate in candidates:
        if all((candidate / name).is_file() for name in required):
            return str(candidate.resolve())
    raise ValueError('Cannot find OpenRGB.exe, PawnIOLib.dll and SmbusPIIX4.bin together. '
                     'Set openrgb_dir in bridge-config.json to your OpenRGB folder. '
                     'Install OpenRGB with its PawnIO driver; Intel SMBus is not supported.')
