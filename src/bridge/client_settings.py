"""Edit only the saved localhost SDK connection, with atomic writes and backups.
SPDX-License-Identifier: GPL-2.0-or-later
"""
import json
import os
from pathlib import Path
import shutil
import uuid


def settings_path(explicit=None):
    if explicit:
        return Path(explicit).expanduser().resolve()
    if not os.environ.get('APPDATA'):
        raise ValueError('APPDATA is unavailable; specify --settings-file')
    return Path(os.environ['APPDATA']) / 'OpenRGB' / 'OpenRGB.json'


def configure_client(path, port, remove=False):
    path = Path(path)
    if path.exists():
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    elif remove:
        return {'settings_file': str(path), 'changed': False}
    else:
        data = {}
    if not isinstance(data, dict):
        raise ValueError('OpenRGB settings must be a JSON object')
    client = data.get('Client')
    if client is None:
        client = {}
    if not isinstance(client, dict) or not isinstance(client.get('clients', []), list):
        raise ValueError('Unexpected OpenRGB Client settings; original file unchanged')
    previous = client.get('clients', [])
    entries = [entry for entry in previous if not (isinstance(entry, dict)
               and entry.get('ip') in ('127.0.0.1', 'localhost') and entry.get('port') == port)]
    if not remove:
        entries.append({'ip': '127.0.0.1', 'port': port})
    if entries == previous:
        return {'settings_file': str(path), 'changed': False}
    backup = None
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + '.bridge-backup-' + uuid.uuid4().hex)
        shutil.copy2(path, backup)
    client['clients'] = entries
    data['Client'] = client
    temporary = path.with_name(path.name + '.bridge-tmp-' + uuid.uuid4().hex)
    try:
        temporary.write_text(json.dumps(data, indent=4, ensure_ascii=False) + '\n', encoding='utf-8')
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {'settings_file': str(path), 'changed': True, 'backup': str(backup) if backup else None}
