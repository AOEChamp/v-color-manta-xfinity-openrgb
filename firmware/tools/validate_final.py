"""Offline final-image validation; no physical hardware access."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / '_internal'))
from unittest.mock import patch
import firmware_image as final
import final_installer as stock
import test_firmware as firmware_test
import test_installer as installer_test
import test_dimm_selection as selection_test
import test_flicker as flicker_test

if __name__ == '__main__':
    selection_test.run()
    firmware_test.run()
    with patch.multiple(installer_test.installer, build=final.build,
                        OUTPUT=final.OUTPUT, ORDER=stock.ORDER, READS=stock.READS):
        installer_test.run()

    flicker_test.run()

    print('All offline firmware, selection, and installer checks passed. No hardware was accessed.')
