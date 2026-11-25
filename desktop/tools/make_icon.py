"""Draw the desktop app icon (1024 x 1024 PNG with transparency): the site's logo (tools/make_icons.py — green
square, four sound bars) as a macOS-style rounded square with the standard margin, 3 x 3 samples per pixel.
Then `npx tauri icon src-tauri/app-icon.png -o src-tauri/icons` makes every size for macOS and Windows.

usage (from desktop/): python3 tools/make_icon.py"""
import struct, zlib
from pathlib import Path

GREEN, WHITE = (31, 157, 85), (255, 255, 255)
BARS = [(7, 14, 20), (13, 8, 24), (19, 11, 22), (25, 14, 18)]  # x, y0, y1 on a 32-unit grid; stroke 3, round caps
SIZE, SS = 1024, 3
INSET, BOX = 100, 824            # Apple's icon grid: an 824 px rounded square in 1024
RADIUS = BOX * 0.2237


def in_box(x, y):
    # rounded square: inside the straight parts, or within RADIUS of a corner's centre
    x, y = x - INSET, y - INSET
    if not (0 <= x <= BOX and 0 <= y <= BOX):
        return False
    cx = min(max(x, RADIUS), BOX - RADIUS)
    cy = min(max(y, RADIUS), BOX - RADIUS)
    return (x - cx) ** 2 + (y - cy) ** 2 <= RADIUS ** 2


def white(x, y):
    gx, gy = (x - INSET) / BOX * 32, (y - INSET) / BOX * 32
    gx, gy = 16 + (gx - 16) / .72, 16 + (gy - 16) / .72
    for bx, y0, y1 in BARS:
        dy = min(max(gy, y0), y1)
        if (gx - bx) ** 2 + (gy - dy) ** 2 <= 2.25:
            return True
    return False


def main():
    rows = bytearray()
    offs = [(i + .5) / SS for i in range(SS)]
    for y in range(SIZE):
        rows.append(0)
        for x in range(SIZE):
            inside = whites = 0
            for oy in offs:
                for ox in offs:
                    px, py = x + ox, y + oy
                    if in_box(px, py):
                        inside += 1
                        whites += white(px, py)
            if not inside:
                rows += b'\0\0\0\0'
                continue
            a = whites / inside
            rows += bytes(round(g + (w - g) * a) for g, w in zip(GREEN, WHITE)) + bytes([round(255 * inside / SS / SS)])
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', SIZE, SIZE, 8, 6, 0, 0, 0)) + \
        chunk(b'IDAT', zlib.compress(bytes(rows), 9)) + chunk(b'IEND', b'')
    out = Path(__file__).resolve().parent.parent / 'src-tauri' / 'app-icon.png'
    out.write_bytes(png)
    print(out, len(png), 'bytes')


if __name__ == '__main__':
    main()
