"""Offline final-image validation; no physical hardware access."""
from unittest.mock import patch
import build_e000_v2_firmware as final
import second_dimm_e000_v2 as stock
import test_e000_v2_firmware as firmware_test
import test_e000_installer as installer_test
import test_dimm_selection as selection_test

if __name__ == '__main__':
    selection_test.run()
    firmware_test.run()
    with patch.multiple(installer_test.installer, build=final.build,
                        OUTPUT=final.OUTPUT, ORDER=stock.ORDER, READS=stock.READS):
        installer_test.run()
