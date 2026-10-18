"""Read and validate a supported controller identity and lighting state."""
import transport as module

TARGET = 0x71


def snapshot(bus, address):
    signature = bus.read(address, 0xB500, 5)
    chip = bus.read(address, 0x4000, 2)
    if signature != module.SIGNATURE or chip != bytes.fromhex('7730'):
        raise RuntimeError(f'Unexpected identity at {address:#x}')
    return dict(address=hex(address), signature=signature.hex(), chip=chip.hex(),
                mode=bus.read(address, 0xE020, 4).hex(),
                colors=bus.read(address, 0xE300, 24).hex())

