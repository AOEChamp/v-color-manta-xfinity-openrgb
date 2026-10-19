"""Send a volatile RGB command to the experimental Pebble Pro firmware.

Uses HID control SET_REPORT, never interrupt OUT or firmware update commands.
Stock firmware has no acknowledgment; success only confirms USB transfer.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
import json
import secrets
import struct


class Info(c.Structure):
    pass


Info._fields_ = [('path', c.c_char_p), ('vendor', c.c_ushort),
    ('product', c.c_ushort), ('serial', c.c_wchar_p),
    ('release', c.c_ushort), ('manufacturer', c.c_wchar_p),
    ('name', c.c_wchar_p), ('usage_page', c.c_ushort),
    ('usage', c.c_ushort), ('interface', c.c_int), ('next', c.POINTER(Info))]

MODES={'static':0,'cycle':1,'pulse':2,'off':3}

def make_report(color,mode=None,save=False):
    if len(color)!=3:raise ValueError('Expected three RGB bytes')
    if save:
        return b'\x03RGB\x03\x01'+color+bytes([MODES[mode or 'static'],1])+bytes(53)
    # No --mode preserves the installed v1 static protocol.
    if mode is None:return b'\x03RGB\x01\x01'+color+bytes(55)
    return b'\x03RGB\x02\x01'+color+bytes([MODES[mode]])+bytes(54)

def query_report(nonce):
    if len(nonce)!=3:raise ValueError('Expected three nonce bytes')
    return b'\x03RGB\x03\x02'+nonce+bytes(55)

def parse_reply(report,nonce):
    if len(report)!=64 or report[:7]!=bytes.fromhex('0352474203820f') or report[28:31]!=nonce:
        raise ValueError('Unrecognized or mismatched custom firmware reply')
    magic,word,complement=struct.unpack_from('<III',report,16)
    saved=None
    if magic==0x33504752 and complement==word^0xffffffff and 1<=word>>24<=4:
        mode=(word>>24)-1
        saved=dict(mode=next(k for k,v in MODES.items() if v==mode),
                   rgb=bytes([word&255,(word>>8)&255,(word>>16)&255]).hex())
    return dict(custom_firmware=True,protocol=3,capabilities=report[6],
                active_native_mode_raw=report[7],instantaneous_rgb=report[8:11].hex(),
                host_target_rgb=report[12:15].hex(),host_target_valid=report[7] in (254,255),saved=saved,
                saved_record_valid=saved is not None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('color',nargs='?',help='six hexadecimal RGB digits, e.g. FF0000')
    parser.add_argument('--mode',choices=MODES,help='Requires the newer mode-capable firmware; cycle ignores RGB')
    parser.add_argument('--save',action='store_true',help='Save as power-on default; requires persistence firmware')
    parser.add_argument('--read',action='store_true',help='Read identity/current/saved state; requires persistence firmware')
    args = parser.parse_args()
    if args.read and (args.color is not None or args.mode or args.save):parser.error('--read is a separate command')
    if not args.read and args.color is None:parser.error('Provide RGB color or --read')
    color = bytes.fromhex(args.color.removeprefix('#')) if args.color else bytes(3)
    if len(color) != 3:
        parser.error('Color must contain exactly three bytes')
    api = c.CDLL(r'C:\Program Files\OpenRGB\hidapi-hotplug.dll')
    api.hid_enumerate.argtypes = [c.c_ushort, c.c_ushort]
    api.hid_enumerate.restype = c.POINTER(Info)
    api.hid_free_enumeration.argtypes = [c.POINTER(Info)]
    head = api.hid_enumerate(0x041e, 0x3287)
    paths = []
    try:
        item = head
        while item:
            info = item.contents
            if info.interface == 0 and info.usage_page == 1 and info.usage == 0:
                paths.append(info.path.decode())
            item = info.next
    finally:
        api.hid_free_enumeration(head)
    if len(paths) != 1:
        raise RuntimeError(f'Expected exactly one Pebble RGB HID collection; got {len(paths)}')
    kernel = c.WinDLL('kernel32', use_last_error=True)
    hid = c.WinDLL('hid', use_last_error=True)
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p,
                                  w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    hid.HidD_SetOutputReport.argtypes = [w.HANDLE, c.c_void_p, w.ULONG]
    hid.HidD_SetOutputReport.restype = w.BOOLEAN
    read_handle=None
    if args.read:
        api.hid_open_path.argtypes=[c.c_char_p];api.hid_open_path.restype=c.c_void_p
        api.hid_close.argtypes=[c.c_void_p]
        api.hid_read_timeout.argtypes=[c.c_void_p,c.c_void_p,c.c_size_t,c.c_int]
        api.hid_read_timeout.restype=c.c_int
        read_handle=api.hid_open_path(paths[0].encode())
        if not read_handle:raise RuntimeError('Could not open HID input collection')
    handle = kernel.CreateFileW(paths[0], 0xc0000000, 3, None, 3, 0, None)
    if handle == c.c_void_p(-1).value:
        if read_handle:api.hid_close(read_handle)
        raise c.WinError(c.get_last_error())
    nonce=secrets.token_bytes(3)
    report = query_report(nonce) if args.read else make_report(color,args.mode,args.save)
    assert len(report) == 64
    try:
        buffer = c.create_string_buffer(report, 64)
        if not hid.HidD_SetOutputReport(handle, buffer, len(report)):
            raise c.WinError(c.get_last_error())
        if args.read:
            received=(c.c_ubyte*64)()
            length=api.hid_read_timeout(read_handle,received,64,2000)
            if length!=64:raise RuntimeError(f'No complete custom-firmware reply (result {length}); retry if busy')
            print(json.dumps(parse_reply(bytes(received),nonce),indent=2))
    finally:
        kernel.CloseHandle(handle)
        if read_handle:api.hid_close(read_handle)
    if args.read:return
    print(json.dumps(dict(usb_control_transfer_succeeded=True,
                         rgb=color.hex(), path=paths[0],
                         mode=args.mode or ('static (v3)' if args.save else 'static (legacy v1)'),
                         save_requested=args.save,
                         visible_effect_requires_confirmation=True), indent=2))


if __name__ == '__main__':
    main()
