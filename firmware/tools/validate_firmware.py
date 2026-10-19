"""Offline patched-v1 validation; no physical hardware access."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / '_internal'))
import test_firmware
import test_installer
import test_dimm_selection
import test_flicker

if __name__ == '__main__':
    test_dimm_selection.run()
    test_firmware.run()
    test_installer.run()
    test_flicker.run()
    print('All offline firmware, selection, and installer checks passed. No hardware was accessed.')
