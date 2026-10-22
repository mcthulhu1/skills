"""Renders assets/icon.png: python3 assets/make_icon.py assets/icon.png (needs Pillow)."""
import sys
from PIL import Image, ImageDraw
S = 4096; k = S / 1024
def s(*v): return [x * k for x in v]
img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
# background: vertical gradient teal -> deep indigo, rounded square
grad = Image.new('RGBA', (S, S))
gd = ImageDraw.Draw(grad)
top, bot = (20, 122, 128), (34, 28, 82)
for y in range(S):
    t = y / (S - 1)
    gd.line([(0, y), (S, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bot)) + (255,))
mask = Image.new('L', (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle(s(0, 0, 1024, 1024), radius=230 * k, fill=255)
img.paste(grad, (0, 0), mask)
d = ImageDraw.Draw(img)
# document sheet with folded corner
x0, y0, x1, y1, f = 262, 170, 762, 854, 120
sheet = (247, 244, 236, 255)
d.polygon(s(x0, y0, x1 - f, y0, x1, y0 + f, x1, y1, x0, y1), fill=sheet)
d.polygon(s(x1 - f, y0, x1 - f, y0 + f, x1, y0 + f), fill=(205, 198, 182, 255))
# verbatim requirement: an opening quotation mark, top-left
ink = (34, 28, 82, 255)
for cx in (346, 412):  # opening quotation mark: dot with a tail rising to the right
    d.ellipse(s(cx - 26, 274, cx + 26, 326), fill=ink)
    d.polygon(s(cx - 24, 292, cx + 8, 230, cx + 30, 240, cx + 10, 300), fill=ink)
# text lines to the right of the quote
for i, w in enumerate((200, 150)):
    yy = 254 + i * 46
    d.rounded_rectangle(s(452, yy, 452 + w, yy + 22), radius=11 * k, fill=(150, 146, 170, 255))
# chain: verbatim requirement (quote above) -> facts -> decision -> plan -> change -> verification (seal)
nodes = [(342, 410), (342, 510), (342, 610), (342, 710)]
d.line(s(*nodes[0], *nodes[-1]), fill=ink, width=int(16 * k))
for i, (cx, cy) in enumerate(nodes):
    r = 30
    d.ellipse(s(cx - r, cy - r, cx + r, cy + r), fill=ink)
    d.ellipse(s(cx - r + 13, cy - r + 13, cx + r - 13, cy + r - 13), fill=sheet)
    w = (230, 200, 170, 140)[i]
    d.rounded_rectangle(s(404, cy - 11, 404 + w, cy + 11), radius=11 * k, fill=(150, 146, 170, 255))
# verification seal bottom-right overlapping the sheet edge
cx, cy, r = 740, 790, 132
d.ellipse(s(cx - r - 16, cy - r - 16, cx + r + 16, cy + r + 16), fill=sheet)
d.ellipse(s(cx - r, cy - r, cx + r, cy + r), fill=(240, 160, 48, 255))
d.line(s(cx - 62, cy + 2, cx - 16, cy + 50, cx + 66, cy - 46), fill=ink, width=int(36 * k), joint='curve')
for px, py in ((cx - 62, cy + 2), (cx - 16, cy + 50), (cx + 66, cy - 46)):
    rr = 18
    d.ellipse(s(px - rr, py - rr, px + rr, py + rr), fill=ink)
img.resize((1024, 1024), Image.LANCZOS).save(sys.argv[1], optimize=True)
