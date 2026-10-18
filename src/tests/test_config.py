"""Configuration, discovery and shared-port regression tests; no RAM access."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
from config import load_config, find_openrgb
from ene_aura6 import PawnBus


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'settings.json'

    def load(self, data):
        self.config.write_text(json.dumps(data), encoding='utf-8')
        return load_config(self.config)

    def test_public_configuration_needs_only_path_and_ports(self):
        data = self.load({})
        self.assertEqual(data, {'openrgb_dir':None, 'port':6743, 'smbus_port':0})

    def test_rejects_invalid_configuration(self):
        for data in ([], {'port': True}, {'port': 0}, {'smbus_port': 2},
                     {'openrgb_dir': 1}, {'typo': 1}):
            with self.subTest(data=data), self.assertRaises(ValueError): self.load(data)

    def test_relative_path_is_relative_to_config_not_working_directory(self):
        self.assertEqual(self.load({'openrgb_dir': 'portable OpenRGB'})['openrgb_dir'],
                         str((self.root/'portable OpenRGB').resolve()))

    def test_portable_discovery_requires_all_transport_files(self):
        folder = self.root / 'OpenRGB'
        folder.mkdir()
        for name in ('OpenRGB.exe','PawnIOLib.dll','SmbusPIIX4.bin'):
            (folder / name).touch()
        self.assertEqual(find_openrgb(root=self.root), str(folder.resolve()))
        (folder/'SmbusPIIX4.bin').unlink()
        with self.assertRaises(ValueError): find_openrgb(str(folder))

    def test_explicit_bad_path_does_not_silently_fall_back(self):
        with self.assertRaises(ValueError): find_openrgb(str(self.root/'missing'))

    def test_missing_explicit_config_fails(self):
        with self.assertRaises(ValueError): load_config(self.config)

    def test_port_reselected_under_mutex_on_every_transaction(self):
        bus = PawnBus.__new__(PawnBus)
        bus.lock, bus.port, bus.mutex = threading.RLock(), 1, 123
        bus.kernel = Mock()
        bus.kernel.WaitForSingleObject.return_value = 0
        events = []
        bus.execute = lambda *args: events.append(args)
        for _ in range(2):
            with bus.transaction(): events.append('work')
        self.assertEqual(events, [('ioctl_piix4_port_sel',[1],1),'work']*2)
        self.assertEqual(bus.kernel.ReleaseMutex.call_count, 2)

    def test_failed_port_selection_releases_mutex(self):
        bus = PawnBus.__new__(PawnBus)
        bus.lock, bus.port, bus.mutex = threading.RLock(), 0, 123
        bus.kernel = Mock()
        bus.kernel.WaitForSingleObject.return_value = 0
        bus.execute = Mock(side_effect=OSError('port selection failed'))
        with self.assertRaises(OSError):
            with bus.transaction(): self.fail('must not access hardware')
        bus.kernel.ReleaseMutex.assert_called_once_with(123)

    def test_service_owned_mutex_opens_with_only_required_access(self):
        dll, kernel = Mock(), Mock()
        dll.pawnio_open.return_value = dll.pawnio_load.return_value = 0
        kernel.CreateMutexW.return_value = 0  # Existing SYSTEM mutex denies full access.
        kernel.CreateMutexExW.return_value = 123
        kernel.WaitForSingleObject.return_value = 0
        with patch('ene_aura6.c.WinDLL', side_effect=[dll,kernel], create=True), \
             patch.object(Path, 'read_bytes', return_value=b'module'), \
             patch.object(PawnBus, 'execute', return_value=[0]):
            bus = PawnBus(self.root)
            bus.close()
        kernel.CreateMutexW.assert_not_called()
        kernel.CreateMutexExW.assert_called_once_with(None, r'Global\Access_SMBUS.HTP.Method', 0, 0x00100001)
        kernel.ReleaseMutex.assert_called_once_with(123)
        kernel.CloseHandle.assert_called_once_with(123)


if __name__ == '__main__': unittest.main()
