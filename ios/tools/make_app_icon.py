"""Draw the iOS app icon (1024 x 1024, opaque RGB): the same logo as tools/make_icons.py (green square, four sound
bars), full bleed with the logo in the safe zone (iOS rounds the corners itself), 4 x 4 samples per pixel.

usage: python3 ios/tools/make_app_icon.py   (writes ios/Flow/Assets.xcassets/AppIcon.appiconset/icon-1024.png)"""
import struct, zlib
from pathlib import Path

GREEN, WHITE = (31, 157, 85), (255, 255, 255)
BARS = [(7, 14, 20), (13, 8, 24), (19, 11, 22), (25, 14, 18)]  # x, y0, y1 on a 32-unit grid; stroke 3, round caps
SIZE, SS = 1024, 4


def white(gx, gy):
    gx, gy = 16 + (gx - 16) / .72, 16 + (gy - 16) / .72
    for bx, y0, y1 in BARS:
        dy = min(max(gy, y0), y1)
        if (gx - bx) ** 2 + (gy - dy) ** 2 <= 2.25:
            return True
    return False


def main():
    u = 32 / SIZE
    rows = bytearray()
    for y in range(SIZE):
        rows.append(0)
        for x in range(SIZE):
            n = sum(white((x + (i + .5) / SS) * u, (y + (j + .5) / SS) * u) for i in range(SS) for j in range(SS))
            a = n / (SS * SS)
            rows += bytes(round(g + (w - g) * a) for g, w in zip(GREEN, WHITE))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', SIZE, SIZE, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(bytes(rows), 9)) + chunk(b'IEND', b'')
    out = Path(__file__).resolve().parents[1] / 'Flow' / 'Assets.xcassets' / 'AppIcon.appiconset' / 'icon-1024.png'
    out.write_bytes(png)
    print(out, len(png), 'bytes')


if __name__ == '__main__':
    main()
