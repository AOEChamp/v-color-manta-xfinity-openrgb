from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from package_release import WINDOWS_FILES, package


class PackageTests(unittest.TestCase):
    def test_only_end_user_files_are_copied(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root/'build/runtime/VColorOpenRGBBridge'
            files = [root/'src/windows'/n for n in WINDOWS_FILES]
            files += [root/n for n in ('LICENSE','THIRD_PARTY_NOTICES.md')]
            files += [root/'src/licenses'/n for n in ('PYTHON-LICENSE.txt','PYINSTALLER-COPYING.txt')]
            files += [runtime/'VColorOpenRGBBridge.exe',runtime/'_internal/python312.dll',
                      root/'src/research/private.txt',root/'src/windows/bridge-config.json']
            for file in files:
                file.parent.mkdir(parents=True,exist_ok=True)
                file.write_bytes(b'fixture')
            output = package(root)
            self.assertTrue((output/'VColorOpenRGBBridge.exe').is_file())
            self.assertFalse((output/'bridge-config.json').exists())
            self.assertFalse((output/'src').exists())
            self.assertEqual(list(root.glob('*.zip')),[])


if __name__ == '__main__': unittest.main()
