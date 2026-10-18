"""Offline v2-to-v3 upgrade, settings preservation and failure guards."""
from unittest.mock import patch
from firmware_image import build as build_v2, SOURCE, ROOT
from firmware_v3 import build, OUTPUT
from test_dimm_selection import Physical
from flash_v2 import TargetBus
import bootloader as boot
import upgrade_v3


def run():
    original = SOURCE.read_bytes()
    parent, _ = build_v2(original)
    candidate, _ = build(original)
    assert candidate == OUTPUT.read_bytes()
    assert [a for a in range(0,65536,128) if parent[a:a+128] != candidate[a:a+128]] == [0x2000,0x3480]
    saved = (ROOT.parent/'tests/fixtures/saved-static-red.bin').read_bytes()
    cases = 0
    for target in (0x71,0x73):
        for fault in (None,'preflight','readback','error','uncertain','stock','already-v3'):
            physical = Physical(target, fault)
            physical.inner.flash[:] = original if fault == 'stock' else candidate if fault == 'already-v3' else parent
            physical.inner.flash[0xE000:0xE180] = saved
            if fault == 'preflight':
                physical.inner.flash[0x4180] ^= 1
            bus, report = TargetBus(physical,target), {}
            try:
                with patch.object(boot.time,'sleep',lambda _:None):
                    boot.run(bus,report,lambda:None,cpu_only=True,
                             verified_action=upgrade_v3.install,control=False)
            except (RuntimeError,OSError):
                assert fault is not None
            else:
                assert fault is None
                expected = bytearray(candidate)
                expected[0xE000:0xE180] = saved
                assert physical.inner.flash == expected
                assert physical.inner.programmed == list(upgrade_v3.ORDER)
                assert report['saved_settings_preserved'] and report['application_resumed']
                assert report['protection_restored']
            if fault in ('stock','already-v3','preflight'):
                assert not physical.inner.programmed
                assert report['application_resumed']
            elif fault is not None:
                assert report['firmware_update_incomplete']
                assert report['exit_deferred_incomplete_firmware']
                assert not report.get('exit_writes')
                if fault == 'uncertain':
                    assert report['flash_request_unresolved']
                    assert report['protection_restore_deferred_pending_flash']
            assert bytes(physical.inner.flash[0xE000:0xE180]) == saved
            assert all(address == target for address in physical.writes)
            cases += 1
    print(f'V3 upgrade: {cases} selected-target, settings and fault cases passed; no hardware access.')
