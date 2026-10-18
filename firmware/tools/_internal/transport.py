"""SMBus transport through the PawnIO installation supplied by OpenRGB.
SPDX-License-Identifier: GPL-2.0-or-later
"""
import ctypes as c
import pathlib
import threading
from contextlib import contextmanager

SIGNATURE = bytes.fromhex('a8 32 16 e8 8c')

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

    def close(self):
        if self.handle.value:
            self.dll.pawnio_close(self.handle)
            self.handle.value = None
        if self.mutex:
            self.kernel.CloseHandle(self.mutex)
            self.mutex = None
