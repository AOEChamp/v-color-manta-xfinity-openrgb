import sys
import pathlib
import threading
import unittest
import struct
from unittest.mock import patch
from contextlib import nullcontext
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'bridge'))
from ene_aura6 import Dimm, SIGNATURE, color_frame, discover, PawnBus
from openrgb_bridge import Server, update, mode_description
from modes import MODES

class FakeBus:
    def __init__(self): self.calls = []; self.signature = SIGNATURE
    def transaction(self): return nullcontext()
    def read(self, addr, reg, n):
        if reg == 0xB500: return self.signature
        if reg == 0xE020: return bytes([0,1,0,0])
        return bytes([10,30,20]*8)
    def block(self, *args): self.calls.append(('block', *args))
    def select(self, *args): self.calls.append(('select', *args))
    def transfer(self, *args): self.calls.append(('transfer', *args))

class Tests(unittest.TestCase):
    def setUp(self): self.bus = FakeBus(); self.d = Dimm(self.bus, 0x71)
    def test_discovery_is_read_only(self):
        self.assertEqual(self.bus.calls, [])
        self.assertEqual(self.d.colors, [(10,20,30)]*8)
    def test_identity_gate(self):
        self.bus.signature = bytes(5)
        with self.assertRaises(ValueError): Dimm(self.bus, 0x71)
        self.assertEqual(self.bus.calls, [])
    def test_recorded_frame(self):
        self.d.apply([(0,0,255)]*8)
        self.assertEqual(self.bus.calls, [('block',0x71,0xE300,bytes([0,255,0]*8)),
            ('block',0x71,0xE020,bytes([0,1,0,0])),('select',0x71,0xE02F),('transfer',0x71,0,1,2,1)])
    def test_invalid_inputs_never_write(self):
        for data in [b'', struct.pack('<IH',38,7)+bytes(32),struct.pack('<IH',37,8)+bytes(32)]:
            with self.assertRaises(ValueError): update(self.d,1050,data)
        with self.assertRaises(ValueError): color_frame([(256,0,0)]*8)
        self.assertEqual(self.bus.calls, [])
    def test_off_preserves_colors(self):
        before = self.d.colors[:]
        self.d.apply(mode=2)
        self.assertEqual(self.bus.calls[0][-1], bytes(24))
        self.d.apply(mode=1)
        self.assertEqual(self.d.colors, before)
        self.assertEqual(self.bus.calls[4][-1], bytes([10,30,20]*8))
    def test_save_applies_then_persists_once(self):
        self.d.colors = [(12,34,56)]*8
        self.d.save(mode=1)
        self.assertEqual(self.bus.calls, [
            ('block',0x71,0xE300,bytes([12,56,34]*8)),
            ('block',0x71,0xE020,bytes([0,1,0,0])),
            ('select',0x71,0xE02F),('transfer',0x71,0,1,2,1),
            ('select',0x71,0xE0A0),('transfer',0x71,0,1,2,0xAA)])
    def test_save_off_persists_black(self):
        self.d.save(mode=2)
        self.assertEqual(self.bus.calls[0][-1], bytes(24))
        self.assertEqual(self.bus.calls[-1], ('transfer',0x71,0,1,2,0xAA))
        self.assertEqual(self.d.colors, [(10,20,30)]*8)
    def test_discovery_does_not_require_firmware_configuration(self):
        with patch.object(self.bus, 'read', side_effect=lambda a,r,n: (SIGNATURE if a in (0x71,0x73) else bytes(5)) if r == 0xB500 else bytes(24)):
            devices = discover(self.bus)
        self.assertEqual([d.address for d in devices], [0x71,0x73])
        self.assertEqual(self.bus.calls, [])
        for device in devices: device.save()
        self.assertEqual([c for c in self.bus.calls if c[0]=='transfer' and c[-1]==0xAA],
                         [('transfer',0x71,0,1,2,0xAA),('transfer',0x73,0,1,2,0xAA)])
    def test_failed_apply_never_persists(self):
        with patch.object(self.bus, 'transfer', side_effect=OSError('apply failed')):
            with self.assertRaises(OSError): self.d.save()
        self.assertNotIn(('select',0x71,0xE0A0), self.bus.calls)

    def test_hardware_effect_transactions_at_both_speed_limits(self):
        for index, spec in enumerate(MODES):
            if not spec.animated: continue
            for speed in (0,4):
                with self.subTest(name=spec.name,speed=speed):
                    self.bus.calls.clear()
                    self.d.apply(mode=index,speed=speed)
                    self.assertEqual(self.bus.calls, [
                        ('block',0x71,0xE300,bytes([10,30,20]*8)),
                        ('block',0x71,0xE020,bytes([0,spec.value,speed,0])),
                        ('select',0x71,0xE02F),('transfer',0x71,0,1,2,1)])

    def test_effect_speed_survives_color_updates_and_save(self):
        index = next(i for i,m in enumerate(MODES) if m.name=='Flashing')
        self.d.apply(mode=index,speed=4)
        self.d.apply([(12,34,56)]*8)
        self.assertEqual(self.bus.calls[-3],('block',0x71,0xE020,bytes([0,3,4,0])))
        self.bus.calls.clear()
        self.d.save()
        self.assertEqual(self.bus.calls[1],('block',0x71,0xE020,bytes([0,3,4,0])))
        self.assertEqual(self.bus.calls[-2:],[('select',0x71,0xE0A0),('transfer',0x71,0,1,2,0xAA)])

    def test_invalid_effect_speed_never_writes(self):
        for mode,speed in ((3,5),(3,-1),(3,True),(1,2),(len(MODES),2)):
            with self.subTest(mode=mode,speed=speed), self.assertRaises(ValueError):
                self.d.apply(mode=mode,speed=speed,persist=True)
        self.assertEqual(self.bus.calls,[])
        for packet in (1101,1102):
            descriptor=mode_description(3,speed=5)
            data=struct.pack('<II',8+len(descriptor),3)+descriptor
            with self.assertRaises(ValueError): update(self.d,packet,data)
        self.assertEqual(self.bus.calls,[])

    def test_failed_effect_apply_does_not_commit_software_state(self):
        with patch.object(self.bus,'transfer',side_effect=OSError('apply failed')):
            with self.assertRaises(OSError): self.d.apply(mode=4,speed=4,persist=True)
        self.assertEqual(self.d.mode,1)
        self.assertEqual(self.d.speeds[4],2)
        self.assertNotIn(('select',0x71,0xE0A0),self.bus.calls)

    def test_discovery_preserves_live_effect_without_writing(self):
        def read(address,register,count):
            if register==0xB500: return SIGNATURE
            if register==0xE020: return bytes([0,13,4,0])
            return bytes([10,30,20]*8)
        with patch.object(self.bus,'read',side_effect=read):
            device=Dimm(self.bus,0x71)
        self.assertEqual(MODES[device.mode].name,'Random Flicker')
        self.assertEqual(device.speeds[device.mode],4)
        self.assertEqual(self.bus.calls,[])
    def test_invalid_save_packets_never_write(self):
        descriptor = mode_description(1)
        valid = struct.pack('<II',8+len(descriptor),1)+descriptor
        for data in (b'', valid[:-1], struct.pack('<II',len(valid),len(MODES))+descriptor,
                     valid[:8]+b'\x00\x00'+valid[10:], valid+b'\0'):
            with self.assertRaises(ValueError): update(self.d,1102,data)
        self.assertEqual(self.bus.calls, [])
    def test_modes_advertise_manual_save(self):
        for i in range(len(MODES)):
            descriptor = mode_description(i)
            name_len = struct.unpack_from('<H',descriptor)[0]
            flags = struct.unpack_from('<I',descriptor,2+name_len+4)[0]
            self.assertTrue(flags & 256)
            self.assertFalse(flags & 512)  # No automatic flash writes.
            self.assertEqual(bool(flags & 1),MODES[i].animated)
            self.assertEqual(bool(flags & 32),MODES[i].colors)
    def test_independent_sdk_client(self):
        from openrgb import OpenRGBClient
        from openrgb.utils import RGBColor
        with Server(0,[self.d,Dimm(self.bus,0x73)]) as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                client=OpenRGBClient(port=server.server_address[1],protocol_version=3)
                self.assertEqual(len(client.devices),2)
                self.assertEqual(len(client.devices[0].leds),8)
                self.assertEqual([m.name for m in client.devices[0].modes],[m.name for m in MODES])
                client.devices[0].set_color(RGBColor(12,34,56))
                self.assertEqual(self.d.colors,[(12,34,56)]*8)
                client.devices[0].zones[0].set_color(RGBColor(45,67,89))
                self.assertEqual(self.d.colors,[(45,67,89)]*8)
                client.devices[0].leds[2].set_color(RGBColor(1,2,3))
                self.assertEqual(self.d.colors[2],(1,2,3))
                client.devices[0].set_mode('Off')
                self.assertEqual(self.d.mode,2)
                self.assertFalse(any(c[0] == 'select' and c[2] == 0xE0A0 for c in self.bus.calls))
                self.bus.calls.clear()
                client.devices[0].save_mode()
                client.devices[0].update()  # Descriptor request waits for preceding save.
                self.assertEqual(self.bus.calls[-1], ('transfer',0x71,0,1,2,0xAA))
                self.assertTrue(all(c[1] == 0x71 for c in self.bus.calls))
                self.bus.calls.clear()
                client.devices[1].save_mode()
                client.devices[1].update()
                self.assertEqual(self.bus.calls[-1], ('transfer',0x73,0,1,2,0xAA))
                self.assertTrue(all(c[1] == 0x73 for c in self.bus.calls))
                self.bus.calls.clear()
                flashing=next(m for m in client.devices[0].modes if m.name=='Flashing')
                self.assertEqual((flashing.speed_min,flashing.speed_max),(4,0))
                flashing.speed=4
                client.devices[0].set_mode(flashing)
                self.assertEqual(MODES[self.d.mode].value,3)
                self.assertEqual(self.d.speeds[self.d.mode],4)
                self.assertEqual(self.bus.calls[1],('block',0x71,0xE020,bytes([0,3,4,0])))
                self.assertTrue(all(c[1] == 0x71 for c in self.bus.calls))
                self.bus.calls.clear()
                client.devices[0].save_mode()
                client.devices[0].update()
                self.assertEqual(self.bus.calls[1],('block',0x71,0xE020,bytes([0,3,4,0])))
                self.assertEqual(self.bus.calls[-1],('transfer',0x71,0,1,2,0xAA))
                flicker=next(m for m in client.devices[0].modes if m.name=='Random Flicker')
                self.assertTrue(flicker.flags & 32)  # Per-LED color control in OpenRGB.
                self.assertEqual(flicker.color_mode,1)
                flicker.speed=4
                client.devices[0].set_mode(flicker)
                self.bus.calls.clear()
                client.devices[0].set_color(RGBColor(12,34,56))
                client.devices[0].update()
                self.assertEqual(self.bus.calls[:2],[
                    ('block',0x71,0xE300,bytes([12,56,34]*8)),
                    ('block',0x71,0xE020,bytes([0,13,4,0]))])
                self.assertFalse(any(c[0]=='select' and c[2]==0xE0A0 for c in self.bus.calls))
                client.disconnect()
            finally: server.shutdown();thread.join()

if __name__=='__main__':unittest.main()
