"""Run the read-only snapshot with only wait/release rights on the bus mutex.

The production bridge source is unchanged. No lighting apply is performed.
"""
import pathlib
import runpy
import sys
import types

root = pathlib.Path(__file__).resolve().parents[1]
source_path = root / 'bridge' / 'ene_aura6.py'
source = source_path.read_text(encoding='utf-8')
source = source.replace(
    'self.kernel.CreateMutexW.argtypes = [c.c_void_p, c.c_bool, c.c_wchar_p]',
    'self.kernel.CreateMutexExW.argtypes = [c.c_void_p, c.c_wchar_p, c.c_uint32, c.c_uint32]')
source = source.replace('self.kernel.CreateMutexW.restype', 'self.kernel.CreateMutexExW.restype')
source = source.replace(
    "self.kernel.CreateMutexW(None, False, r'Global\\Access_SMBUS.HTP.Method')",
    "self.kernel.CreateMutexExW(None, r'Global\\Access_SMBUS.HTP.Method', 0, 0x00100001)")
module = types.ModuleType('ene_aura6')
module.__file__ = str(source_path)
exec(compile(source, str(source_path), 'exec'), module.__dict__)
sys.modules['ene_aura6'] = module
if __name__ == '__main__':
    sys.argv = [str(root / 'tools' / 'lighting_snapshot.py')]
    runpy.run_path(sys.argv[0], run_name='__main__')
