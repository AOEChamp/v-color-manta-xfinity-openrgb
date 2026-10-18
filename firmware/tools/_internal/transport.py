"""Native ENE Aura 6 control through the PawnIO installation supplied by OpenRGB.
No vendor DLLs, EEPROM writes, address remapping, or firmware updates.
SPDX-License-Identifier: GPL-2.0-or-later
"""
import ctypes as c
import pathlib
import threading
from contextlib import contextmanager

SIGNATURE = bytes.fromhex('a8 32 16 e8 8c')
LED_COUNT = 8

def color_frame(colors):
    if len(colors) != LED_COUNT or any(len(v) != 3 or any(type(x) is not int or not 0 <= x <= 255 for x in v) for v in colors):
        raise ValueError('Exactly eight RGB byte triples are required')
    return bytes(x for r, g, b in colors for x in (r, b, g))

class PawnBus:
    def __init__(self, directory=r'C:\Program Files\OpenRGB', port=0):
        self.root = pathlib.Path(directory)
        self.lock = threading.RLock()
        self.dll = c.WinDLL(str(self.root / 'PawnIOLib.dll'))
        self.handle = c.c_void_p()
        self.kernel = c.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateMutexExW.argtypes = [c.c_void_p, c.c_wchar_p, c.c_uint32, c.c_uint32]
        self.kernel.CreateMutexExW.restype = c.c_void_p
        self.kernel.WaitForSingleObject.argtypes = [c.c_void_p, c.c_uint32]
        self.kernel.ReleaseMutex.argtypes = [c.c_void_p]
        self.kernel.CloseHandle.argtypes = [c.c_void_p]
        self.mutex = self.kernel.CreateMutexExW(None, r'Global\Access_SMBUS.HTP.Method', 0, 0x00100001)
        if not self.mutex: raise c.WinError(c.get_last_error())
        self.dll.pawnio_open.argtypes = [c.POINTER(c.c_void_p)]
        self.dll.pawnio_load.argtypes = [c.c_void_p, c.c_void_p, c.c_size_t]
        self.dll.pawnio_close.argtypes = [c.c_void_p]
        self.dll.pawnio_execute.argtypes = [c.c_void_p, c.c_char_p, c.POINTER(c.c_uint64), c.c_size_t, c.POINTER(c.c_uint64), c.c_size_t, c.POINTER(c.c_size_t)]
        try:
            self.check(self.dll.pawnio_open(c.byref(self.handle)))
            blob = (self.root / 'SmbusPIIX4.bin').read_bytes()
            self.check(self.dll.pawnio_load(self.handle, blob, len(blob)))
            with self.transaction():
                self.execute('ioctl_piix4_port_sel', [port], 1)
        except BaseException:
            self.close()
            raise

    @staticmethod
    def check(result):
        if result: raise OSError(f'PawnIO error 0x{result & 0xffffffff:08X}; administrator rights and the installed PawnIO driver are required')

    @contextmanager
    def transaction(self):
        with self.lock:
            status = self.kernel.WaitForSingleObject(self.mutex, 3000)
            if status not in (0, 0x80): raise TimeoutError('SMBus is busy')
            try: yield
            finally: self.kernel.ReleaseMutex(self.mutex)

    def execute(self, name, values, count=5):
        inp = (c.c_uint64 * len(values))(*values)
        out = (c.c_uint64 * count)()
        used = c.c_size_t()
        self.check(self.dll.pawnio_execute(self.handle, name.encode(), inp, len(values), out, count, c.byref(used)))
        return list(out)

    def transfer(self, address, read, command, size, value=0):
        return self.execute('ioctl_smbus_xfer', [address, read, command, size, value, 0, 0, 0, 0])[0]

    def select(self, address, register):
        self.transfer(address, 0, 0, 3, ((register & 255) << 8) | (register >> 8))

    def read(self, address, register, count):
        self.select(address, register)
        return bytes(self.transfer(address, 1, 0x81, 2) & 255 for _ in range(count))

    def block(self, address, register, data):
        if not 1 <= len(data) <= 32: raise ValueError('Invalid SMBus block length')
        self.select(address, register)
        raw = (bytes([len(data)]) + bytes(data)).ljust(40, b'\0')
        values = [int.from_bytes(raw[i:i+8], 'little') for i in range(0, 40, 8)]
        self.execute('ioctl_smbus_xfer', [address, 0, 3, 5] + values)

    def close(self):
        if self.handle.value:
            self.dll.pawnio_close(self.handle)
            self.handle.value = None
        if self.mutex:
            self.kernel.CloseHandle(self.mutex)
            self.mutex = None

class Dimm:
    def __init__(self, bus, address):
        if address not in range(0x70, 0x74): raise ValueError('Not an allowed lighting address')
        self.bus, self.address = bus, address
        self.lock = threading.RLock()
        with bus.transaction():
            if bus.read(address, 0xB500, 5) != SIGNATURE:
                raise ValueError('Unrecognized ENE firmware; writes disabled')
            data = bus.read(address, 0xE300, 24)
        self.colors = [(data[i], data[i+2], data[i+1]) for i in range(0, 24, 3)]
        self.mode = 1

    def apply(self, colors=None, mode=None):
        with self.lock:
            next_colors = list(self.colors if colors is None else colors)
            next_mode = self.mode if mode is None else mode
            if next_mode not in (0, 1, 2): raise ValueError('Unsupported mode')
            frame = color_frame(next_colors)  # Validate even in Off mode.
            if next_mode == 2: frame = bytes(24)
            with self.bus.transaction():
                self.bus.block(self.address, 0xE300, frame)
                self.bus.block(self.address, 0xE020, bytes([0, 1, 0, 0]))
                self.bus.select(self.address, 0xE02F)
                self.bus.transfer(self.address, 0, 1, 2, 1)
            self.colors, self.mode = next_colors, next_mode

def discover(bus):
    devices = []
    for addr in range(0x70, 0x74):
        try: devices.append(Dimm(bus, addr))
        except (OSError, ValueError): continue
    if not devices: raise RuntimeError('No matching A8 32 16 E8 8C DIMMs found on PIIX4 port 0')
    return devices
