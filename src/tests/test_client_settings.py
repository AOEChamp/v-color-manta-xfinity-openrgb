import json
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
from client_settings import configure_client
import openrgb_bridge


class ClientSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'OpenRGB.json'

    def test_install_preserves_settings_and_other_clients_and_is_idempotent(self):
        original = {'Devices': {'A':1, 'a':2}, 'Client': {'custom':True, 'clients':[
            {'ip':'192.0.2.1','port':6742}, {'ip':'localhost','port':6743},
            {'ip':'127.0.0.1','port':6743}]}}
        self.path.write_text(json.dumps(original))
        result = configure_client(self.path,6743)
        self.assertEqual(json.loads(Path(result['backup']).read_text()),original)
        settings = json.loads(self.path.read_text())
        self.assertEqual(settings['Devices'],original['Devices'])
        self.assertEqual(settings['Client']['clients'],[{'ip':'192.0.2.1','port':6742},{'ip':'127.0.0.1','port':6743}])
        self.assertTrue(settings['Client']['custom'])
        self.assertFalse(configure_client(self.path,6743)['changed'])

    def test_uninstall_removes_only_bridge_connection(self):
        self.path.write_text(json.dumps({'Client':{'clients':[{'ip':'127.0.0.1','port':6743},{'ip':'127.0.0.1','port':6742}]}}))
        configure_client(self.path,6743,True)
        self.assertEqual(json.loads(self.path.read_text())['Client']['clients'],[{'ip':'127.0.0.1','port':6742}])

    def test_bad_settings_are_unchanged(self):
        for contents in ('invalid','[]','{"Client": []}','{"Client":{"clients":false}}'):
            self.path.write_text(contents)
            with self.assertRaises(ValueError): configure_client(self.path,6743)
            self.assertEqual(self.path.read_text(),contents)
        self.assertEqual(list(self.path.parent.glob('*.bridge-backup-*')),[])

    def test_first_install_and_missing_uninstall(self):
        self.assertFalse(configure_client(self.path,6743,True)['changed'])
        configure_client(self.path,6743)
        self.assertEqual(json.loads(self.path.read_text()),{'Client':{'clients':[{'ip':'127.0.0.1','port':6743}]}})

    def test_remove_uses_saved_port_without_loading_runtime_config(self):
        configure_client(self.path, 6744)
        configure_client(self.path, 6743)
        argv = ['bridge', '--configure-client', 'remove', '--settings-file', str(self.path), '--port', '6744']
        with patch.object(sys, 'argv', argv), patch.object(openrgb_bridge, 'load_config', side_effect=AssertionError('Runtime config must not be needed')), patch('sys.stdout', new_callable=io.StringIO):
            openrgb_bridge.main()
        self.assertEqual(json.loads(self.path.read_text())['Client']['clients'], [{'ip':'127.0.0.1','port':6743}])


if __name__ == '__main__': unittest.main()
