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


_session = None


def cutout(img_bytes, tol=14, white_tol=2, max_side=700):
    """Cut the garment out of its photo. Returns (RGBA image, share of the image that was background).
    Uses a background-removal model (rembg, isnet-general-use; free, runs on this computer), which
    tells a garment from its soft studio shadow and white fabric from a white backdrop. Falls back
    to the old colour flood-fill when rembg isn't installed."""
    global _session
    try:
        from rembg import remove, new_session
    except ImportError:
        return cutout_flood(img_bytes, tol, white_tol, max_side)
    if _session is None:
        _session = new_session('isnet-general-use')
    im = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    im.thumbnail((1100, 1100))
    rgb = np.asarray(im).astype(float)
    a = np.asarray(remove(im, session=_session).split()[-1]).astype(float)
    # firm up the edge: faint haze goes, nearly solid becomes solid
    a = np.clip((a - 25) * 255 / 205, 0, 255)
    # light fabric on a light backdrop can still lose a bite (a sleeve, a shoulder): fill gaps inside
    # the garment's outline where the colour flood-fill says it is not backdrop either and the pixel
    # looks more like the garment than the backdrop (so a shadowed gap under a dark tee's sleeve
    # stays open). Only well inside the outline, so no backdrop rim comes back.
    solid0 = a > 200
    if solid0.any():
        backdrop = np.median(np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]), axis=0)
        like = np.abs(rgb - np.median(rgb[solid0], axis=0)).max(2) < np.abs(rgb - backdrop).max(2)
        inside = ndimage.binary_erosion(ndimage.binary_closing(a > 40, np.ones((25, 25)), border_value=0), iterations=4)
        a = np.maximum(a, 255 * (inside & like & (_flood_bg(rgb, tol, white_tol) == 0)))

    a = _drop_hanger(rgb, a)

    # keep the garment (and the second shoe of a pair); drop specks and detached shadow bits
    labels, n = ndimage.label(a > 128)
    if n > 1:
        sizes = ndimage.sum(np.ones_like(a), labels, range(1, n + 1))
        keep = np.isin(labels, 1 + np.where(sizes >= sizes.max() * 0.04)[0])
        a[~ndimage.binary_dilation(keep, iterations=3)] = 0

    # edge pixels still carry the old backdrop colour (a light outline on dark clothes):
    # give them the colour of the fabric just inside the edge
    solid = (a >= 250).astype(float)
    num = np.stack([ndimage.gaussian_filter(rgb[..., c] * solid, 3) for c in range(3)], -1)
    den = ndimage.gaussian_filter(solid, 3)[..., None]
    edge = ((a > 0) & (a < 250))[..., None] & (den > 0.02)
    rgb = np.where(edge, num / np.maximum(den, 1e-6), rgb)
    a[(a < 250) & (den[..., 0] <= 0.02)] = 0   # stray edge dots with no fabric next to them

    rgba = Image.fromarray(np.dstack([rgb, a]).round().clip(0, 255).astype('uint8'), 'RGBA')
    rgba = rgba.crop(rgba.split()[-1].point(lambda v: 255 if v > 40 else 0).getbbox())
    rgba.thumbnail((max_side, max_side))
    return rgba, float((a < 128).mean())


def _drop_hanger(rgb, a):
    """Remove a wooden hanger poking out above a collar: wood-coloured pixels in the top part of
    the cut-out that touch its top edge and clearly differ from the garment's own colour (so a
    brown coat keeps its collar). Lettering and highlights on the hanger go with it."""
    on = a > 128
    rows = np.where(on.any(1))[0]
    if not len(rows):
        return a
    top, h = rows[0], rows[-1] - rows[0]
    body = rgb[top + int(h * .3):top + int(h * .6)][on[top + int(h * .3):top + int(h * .6)]]
    if not len(body):
        return a
    garment = np.median(body, axis=0)
    r, mx = rgb[..., 0], rgb.max(2)
    wood = (r - rgb[..., 1:].max(2) > 20) & (mx > 40) & (mx < 245)   # reddish-brown, from dark to pale
    far = np.abs(rgb - garment).max(2) > 60
    zone = np.zeros_like(on)
    zone[top:top + int(h * .15)] = True
    cand = wood & far & on & zone
    blob = ndimage.binary_fill_holes(ndimage.binary_closing(cand, iterations=5)) & on & zone
    labels, n = ndimage.label(blob)
    hit = set(np.unique(labels[top:top + 8])) - {0}
    if not hit:
        return a
    gone = ndimage.binary_dilation(np.isin(labels, list(hit)), iterations=3) & zone
    a = a.copy()
    a[gone] = 0
    return a


def _flood_bg(a, tol, white_tol):
    """Backdrop mask: backdrop-coloured regions that touch the image edge."""
    H, W, _ = a.shape
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    # light garments on light backgrounds need a much tighter tolerance
    centre = a[H // 3:2 * H // 3, W // 3:2 * W // 3].mean()
    t = white_tol if centre > 215 else tol
    labels, _ = ndimage.label(np.abs(a - bg).max(axis=2) <= t)
    edge = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    return np.isin(labels, edge[edge > 0])


def cutout_flood(img_bytes, tol=14, white_tol=2, max_side=700):
    """Old method: remove a plain studio background by flood-filling from the image edges."""
    im = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    im.thumbnail((1100, 1100))
    mask = _flood_bg(np.asarray(im).astype(int), tol, white_tol)
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
