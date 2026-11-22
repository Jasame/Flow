"""Draw Flow's app icons (green rounded square with four sound bars) as PNG, with no image library.

usage: make_icons.py <public dir>"""
import struct, sys, zlib
from pathlib import Path

GREEN, WHITE = (31, 157, 85), (255, 255, 255)


def png(size, pixel):
    rows = b''.join(b'\0' + b''.join(bytes(pixel(x, y, size)) for x in range(size)) for y in range(size))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b'')


def make(maskable):
    # The logo is drawn on a 32-unit grid: bars at x=7,13,19,25 from these y ranges, stroke 3 units, round caps.
    bars = [(7, 14, 20), (13, 8, 24), (19, 11, 22), (25, 14, 18)]

    def pixel(x, y, size):
        u = 32 / size
        gx, gy = (x + .5) * u, (y + .5) * u
        if maskable:  # full-bleed square, logo shrunk into the safe zone
            gx, gy = 16 + (gx - 16) / .72, 16 + (gy - 16) / .72
        else:  # rounded corners, radius 9 units, transparent outside
            cx, cy = min(max(gx, 9), 23), min(max(gy, 9), 23)
            if (gx - cx) ** 2 + (gy - cy) ** 2 > 81:
                return (0, 0, 0, 0)
        for bx, y0, y1 in bars:
            dy = min(max(gy, y0), y1)
            if (gx - bx) ** 2 + (gy - dy) ** 2 <= 2.25:
                return (*WHITE, 255)
        return (*GREEN, 255)
    return pixel


out = Path(sys.argv[1])
for name, size, mask in (('icon-192.png', 192, False), ('icon-512.png', 512, True), ('apple-touch-icon.png', 180, True)):
    (out / name).write_bytes(png(size, make(mask)))
    print(name, (out / name).stat().st_size, 'bytes')
