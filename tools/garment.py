"""Shared helpers for building wardrobe items: size-chart parsing, photo cut-out, photo measuring."""
import re, html, io, json, subprocess
from collections import deque
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

UA = 'Mozilla/5.0'  # some shops answer a full browser signature from a script with 429


def get(url, tries=5):
    """Download a URL; waits and retries when the shop says we're going too fast."""
    import time
    for n in range(tries):
        out = subprocess.run(['curl', '-sL', '-A', UA, '--max-time', '40', '-w', '\n%{http_code}', url],
                             capture_output=True).stdout
        body, _, code = out.rpartition(b'\n')
        if code not in (b'429', b'430', b'503') and b'rate_limited' not in body[:60]:
            return body
        time.sleep(15 * (n + 1))
    return body


def size_tables(body_html):
    """Merge every <table> whose first column is 'Size' into {size: {measure: cm}}."""
    sizes = {}
    for t in re.findall(r'<table.*?</table>', body_html or '', re.S):
        rows = []
        for tr in re.findall(r'<tr.*?</tr>', t, re.S):
            cells = [re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', ' ', c))).strip()
                     for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)]
            if cells:
                rows.append(cells)
        if not rows or rows[0][0].lower() != 'size':
            continue
        head = rows[0]
        for r in rows[1:]:
            for k, v in zip(head[1:], r[1:]):
                m = re.search(r'([\d.]+)\s*cm', v)
                if m:
                    sizes.setdefault(r[0], {})[k.strip().lower()] = float(m.group(1))
    return sizes


CATS = [
    ('shoes', r'shoe|loafer|boot|sneaker|trainer|derby|moc\b|moccasin|sandal|slide|mule'),
    ('jacket', r'jacket|coat|blazer|bomber|parka|overshirt|harrington|cardigan|vest|gilet|chore'),
    ('bottom', r'pant|trouser|jean|chino|\bshorts\b|slacks|cargo'),
    ('top', r'shirt|tee|t-shirt|henley|polo|sweater|sweatshirt|hoodie|knit|jumper|tank|top'),
]


def category(*texts):
    t = ' '.join(x or '' for x in texts).lower()
    for c, rx in CATS:
        if re.search(rx, t):
            return c
    return 'top'


def cutout(img_bytes, tol=14, white_tol=2, max_side=700):
    """Remove a plain studio background by flood-filling from the image edges.
    Returns (RGBA image, share of the image that was background)."""
    im = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    im.thumbnail((1100, 1100))
    a = np.asarray(im).astype(int)
    H, W, _ = a.shape
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    # light garments on light backgrounds need a much tighter tolerance
    centre = a[H // 3:2 * H // 3, W // 3:2 * W // 3].mean()
    t = white_tol if centre > 215 else tol
    cand = np.abs(a - bg).max(axis=2) <= t
    # background = background-coloured regions that touch the image edge
    labels, _ = ndimage.label(cand)
    edge = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    mask = np.isin(labels, edge[edge > 0])
    alpha = Image.fromarray(((~mask) * 255).astype('uint8')).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1))
    rgba = im.convert('RGBA')
    rgba.putalpha(alpha)
    rgba = rgba.crop(alpha.point(lambda v: 255 if v > 40 else 0).getbbox())
    rgba.thumbnail((max_side, max_side))
    return rgba, float(mask.mean())


def measure(rgba, cat):
    """Where the garment sits inside its cut-out, as fractions of the image height.
    top: first opaque row (collar, about shoulder height). hem: bottom of the body at the
    centre column, so sleeves hanging lower are ignored. bottom: last opaque row."""
    al = np.asarray(rgba.split()[-1]) > 60
    H, W = al.shape
    rows = np.where(al.any(axis=1))[0]
    top, bottom = rows[0], rows[-1]
    hem = bottom
    if cat in ('top', 'jacket'):
        band = al[:, int(W * 0.44):int(W * 0.56)]
        r = np.where(band.any(axis=1))[0]
        if len(r):
            hem = r[-1]
    return {'w': W, 'h': H, 'top': round(float(top) / H, 4), 'hem': round(float(hem) / H, 4), 'bottom': round(float(bottom) / H, 4)}
