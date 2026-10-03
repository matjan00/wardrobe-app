"""Import clothes into the wardrobe.

Usage:  python tools/import_items.py import/my-clothes.txt

One piece per line. Blank lines and lines starting with # are skipped. Each line is
a shop link OR a description, optionally followed by fields separated with |

  https://timecatcherco.com/products/1940s-usn-herringbone-deck-pants-navy | size W30
  Levi's 501 jeans, dark indigo | size W31 L32 | inseam 81 | photo levis.jpg
  White Uniqlo oxford shirt | size M | length 74 chest 112

Fields:  size X           the size you own (as the shop writes it)
         photo FILE       a photo in import/photos (laid flat or hung, plain background)
         cat top|bottom|jacket|shoes   if the guess is wrong
         any 'measure number' pairs (length 70, chest 110, waist 82, inseam 81,
         front rise 30) - used when the shop has no size chart
"""
import json, os, re, sys, hashlib, io
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from garment import get, size_tables, category, cutout, measure
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'docs', 'data', 'items.json')
WISH = os.path.join(ROOT, 'docs', 'data', 'wishlist.json')
IMG = os.path.join(ROOT, 'docs', 'img')
PHOTOS = os.path.join(ROOT, 'import', 'photos')

# typical garment measurements (cm) for a size M, used only when nothing better is known
TYPICAL = {
    'top': {'length': 70, 'chest': 108, 'shoulder': 46},
    'jacket': {'length': 68, 'chest': 114, 'shoulder': 47},
    'bottom': {'length': 104, 'waist': 82, 'front rise': 29, 'inseam': 78},
    'shoes': {'length': 29},
}
SHORTS = {'length': 50, 'waist': 82, 'front rise': 28, 'inseam': 20}
COLOURS = {'black': '#1f1f1f', 'white': '#f2f0ea', 'off-white': '#ece6d6', 'ecru': '#e6dcc6', 'cream': '#ebe2cc',
           'navy': '#1f2a40', 'indigo': '#26324f', 'blue': '#3d5f8f', 'light blue': '#a9c1dc', 'denim': '#3c5476',
           'grey': '#8d8d8a', 'gray': '#8d8d8a', 'charcoal': '#3d3e40', 'olive': '#5f6440', 'green': '#3f5d42',
           'khaki': '#b9a77c', 'beige': '#cdb994', 'tan': '#b8875a', 'camel': '#b58a5a', 'brown': '#5e3f2a',
           'chocolate': '#3f2a1f', 'burgundy': '#5d1f2a', 'wine': '#5d1f2a', 'red': '#9c2f2a', 'stone': '#c9c0ae',
           'sand': '#d3c3a1', 'yellow': '#d9b64a', 'orange': '#c46a2b', 'pink': '#d9a3a8', 'purple': '#5b4670'}


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:70] or 'item'


def parse_line(line):
    parts = [p.strip() for p in line.split('|')]
    head, fields = parts[0], {}
    meas = {}
    for p in parts[1:]:
        m = re.match(r'(size|photo|cat|name|brand|paid|price|bought|from|store|colou?r|notes?|priority)\s*:?\s+(.+)$', p, re.I)
        if m:
            fields[m.group(1).lower()] = m.group(2).strip()
            continue
        for k, v in re.findall(r'(front rise|back rise|leg opening|length|chest|shoulder|sleeve|waist|hip|inseam|thigh)\s*:?\s*([\d.]+)', p, re.I):
            meas[k.lower()] = float(v)
    return head, fields, meas


# ---------- reading shop pages ----------
def shopify(url):
    m = re.match(r'(https?://[^/]+)(?:/[a-z]{2}(?:-[a-z]{2})?)?.*?/products/([^/?#]+)', url, re.I)
    if not m:
        return None
    base_path = url.split('?')[0].split('#')[0]
    base_path = base_path[:base_path.index('/products/')] + '/products/' + m.group(2)
    try:
        d = json.loads(get(base_path + '.js'))
    except Exception:
        return None
    imgs = [('https:' + i) if i.startswith('//') else i for i in d.get('images', [])]
    sizes = size_tables(d.get('description', ''))
    if not sizes:  # some shops keep the size chart elsewhere on the page
        try:
            sizes = size_tables(get(url).decode('utf8', 'ignore'))
        except Exception:
            pass
    brand = d.get('vendor') or ''
    if not brand or re.search(r'\d', brand):  # some shops put a product code in the vendor field
        try:
            page = get(url).decode('utf8', 'ignore')
            m = re.search(r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)', page, re.I)
            brand = m.group(1).split('|')[0].strip() if m else ''
        except Exception:
            brand = ''
    return {'title': d.get('title'), 'brand': brand, 'type': d.get('type'), 'images': imgs, 'shop_price': (d.get('price') or 0) / 100 or None,
            'sizes': sizes, 'url': url.split('?')[0]}


def generic(url):
    try:
        page = get(url).decode('utf8', 'ignore')
    except Exception:
        return None
    if len(page) < 500:
        return None
    title = brand = None
    imgs = []
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        for d in (data if isinstance(data, list) else data.get('@graph', [data])):
            if isinstance(d, dict) and 'Product' in str(d.get('@type')):
                title = title or d.get('name')
                b = d.get('brand')
                brand = brand or (b.get('name') if isinstance(b, dict) else b)
                im = d.get('image')
                imgs += im if isinstance(im, list) else [im] if im else []
    def meta(prop):
        m = re.search(r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]+content=["\']([^"\']+)' % prop, page, re.I)
        return m.group(1) if m else None
    title = title or meta('og:title')
    if meta('og:image'):
        imgs.append(meta('og:image'))
    imgs = [i if isinstance(i, str) else i.get('url') for i in imgs if i]
    if not title or not imgs:
        return None
    return {'title': title, 'brand': brand or meta('og:site_name'), 'type': '', 'images': imgs,
            'sizes': size_tables(page), 'url': url}


# ---------- choosing and cutting the photo ----------
def best_cutout(images, cat):
    """Try the first few product photos and keep the cleanest flat shot (plain background,
    garment not touching the edges). Shoes prefer an angled shot of the pair."""
    order = list(images[:6])
    if cat == 'shoes':
        order.sort(key=lambda u: (0 if 'ANGLE' in u.upper() else 1 if 'SIDE' in u.upper() else 2))
    best = None
    for u in order:
        try:
            raw = get(u + ('&' if '?' in u else '?') + 'width=1000') if 'shopify' in u else get(u)
            rgba, bg = cutout(raw)
        except Exception:
            continue
        a = rgba.split()[-1]
        fill = (np.asarray(a) > 60).mean()
        score = bg - (0.4 if fill > 0.92 else 0)   # a full-frame photo usually means a model/lifestyle shot
        if best is None or score > best[0]:
            best = (score, rgba, u)
        if bg > 0.45 and fill < 0.9:
            break
    return best


def placeholder(cat, colour, shorts=False, long_sleeves=False):
    """Simple flat silhouette in the right colour when there is no photo yet."""
    W, H = 600, 700
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = colour
    if cat in ('top', 'jacket') and long_sleeves:
        d.polygon([(170, 20), (250, 0), (350, 0), (430, 20), (560, 300), (590, 640), (520, 650), (450, 330), (450, 690), (150, 690), (150, 330), (80, 650), (10, 640), (40, 300)], fill=c)
        if cat == 'jacket':
            d.line([(300, 40), (300, 690)], fill=(0, 0, 0, 90), width=4)
    elif cat in ('top', 'jacket'):
        d.polygon([(170, 20), (250, 0), (350, 0), (430, 20), (590, 230), (520, 290), (450, 200), (450, 690), (150, 690), (150, 200), (80, 290), (10, 230)], fill=c)
        if cat == 'jacket':
            d.line([(300, 40), (300, 690)], fill=(0, 0, 0, 90), width=4)
    elif cat == 'bottom':
        h = 380 if shorts else 690
        d.polygon([(150, 0), (450, 0), (470, h), (320, h), (300, 230), (280, h), (130, h)], fill=c)
    else:
        W, H = 600, 300
        im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for x in (40, 320):
            d.rounded_rectangle([x, 120, x + 250, 260], 60, fill=c)
            d.rectangle([x, 240, x + 250, 270], fill=(30, 30, 30, 255))
    return im.crop(im.getbbox())


def colour_of(text):
    t = text.lower()
    for name in sorted(COLOURS, key=len, reverse=True):
        if re.search(r'\b%s\b' % re.escape(name), t):
            h = COLOURS[name].lstrip('#')
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    return (150, 150, 150, 255)


# ---------- main ----------
def clean_brand(b):
    b = re.sub(r'\s+(clothing|co\.?|company|official|store|shop)$', '', re.sub(r'\s+\d{4}$', '', (b or '').strip()), flags=re.I)
    return KNOWN_BRANDS.get(b.lower().replace(' ', ''), b)


KNOWN_BRANDS = {'timecatcher': 'Timecatcher', 'g.h.bass': 'G.H.Bass', 'ghbass': 'G.H.Bass', 'uniqlo': 'Uniqlo'}


def money(v):
    m = re.search(r'[\d]+(?:[.,]\d+)?', v or '')
    return float(m.group(0).replace(',', '.')) if m else None


def main(path, wishlist=False):
    target = WISH if wishlist else DATA
    db = json.load(open(target)) if os.path.exists(target) else {'version': 1, 'items': []}
    by_id = {i['id']: i for i in db['items']}
    report = []
    for n, line in enumerate(open(path, encoding='utf8'), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        head, f, meas = parse_line(line)
        is_url = head.lower().startswith('http')
        info = (shopify(head) or generic(head)) if is_url else None
        if is_url and not info:
            report.append((n, 'FAILED', head, "couldn't read this page; add a description and photo instead"))
            continue
        title = f.get('name') or (info['title'] if info else head)
        title = re.split(r'\s+[|–-]\s+(?=[A-Z][A-Za-z ]+$)', title)[0].strip()  # drop " | SHOP NAME" endings
        if info:  # shops often keep the colour only in the link, e.g. ...-deck-pants-navy
            words = info['url'].rstrip('/').split('/')[-1].split('-')
            cands = [' '.join(words[i:i + 2]) for i in range(len(words) - 4, len(words) - 1)] + words[-3:]
            tail = next((c for c in cands if c in COLOURS), None)
            if tail and tail not in title.lower():
                title = '%s, %s' % (title, tail)
        cat = f.get('cat') or category(info['type'] if info else '', title)
        is_shorts = bool(re.search(r'\bshorts\b', title, re.I))
        iid = slug((clean_brand(info['brand']) + ' ' if info and info.get('brand') else '') + title)
        if info:  # the same shop product imported before keeps its id (and saved outfits)
            handle = info['url'].rstrip('/').split('/')[-1]
            same = [i for i in by_id.values() if i.get('url', '').rstrip('/').split('/')[-1] == handle]
            if same:
                iid = same[0]['id']
        notes, est = [], False

        # photo: user's own photo first, then the shop's photos, then a placeholder
        rgba = None
        if f.get('photo'):
            p = os.path.join(PHOTOS, f['photo'])
            if os.path.exists(p):
                rgba, bg = cutout(open(p, 'rb').read(), tol=22)
                if bg < 0.3:
                    notes.append('photo background was busy, cut-out may be rough')
            else:
                notes.append('photo %s not found' % f['photo'])
        if rgba is None and info:
            b = best_cutout(info['images'], cat)
            if b:
                rgba = b[1]
                if b[0] < 0.3:
                    notes.append('shop photo is not a clean flat shot, check it')
                elif 'shopify' not in b[2]:
                    notes.append('photo taken from the page preview, check it is the item and not a model')
        placeholder_used = rgba is None
        if placeholder_used:
            long_sl = bool(re.search(r'sweater|sweatshirt|hoodie|jumper|knit|long.sleeve|shirt|oxford|flannel|jacket|coat|cardigan|overshirt', title, re.I)) and not re.search(r't-?shirt|tee', title, re.I)
            rgba = placeholder(cat, colour_of(title), is_shorts, long_sl)
            notes.append('placeholder shape; add a photo for the real look')
        rgba.thumbnail((700, 700))
        rgba.save(os.path.join(IMG, iid + '.webp'), quality=86, method=6)

        # measurements: shop size chart, else the user's numbers, else typical ones
        sizes = (info or {}).get('sizes') or {}
        size = f.get('size')
        if cat == 'shoes' and not sizes:
            sizes = {str(eu): {'length': round((eu - 2) / 1.5 + 3, 1)} for eu in range(38, 48)}
        if meas:
            sizes = {**sizes, (size or 'yours'): {**sizes.get(size or 'yours', {}), **meas}}
            size = size or 'yours'
        if not sizes:
            sizes = {size or 'typical': dict(SHORTS if is_shorts else TYPICAL[cat])}
            size = size or 'typical'
            est = True
        if size and size not in sizes:
            match = [k for k in sizes if k.lower().replace(' ', '') == size.lower().replace(' ', '')]
            if match:
                size = match[0]
            else:
                notes.append('size %s not in the size chart (%s)' % (size, ', '.join(sizes)))

        rec = {'id': iid, 'name': title, 'brand': clean_brand(f.get('brand') or (info or {}).get('brand')),
               'cat': cat, 'img': 'img/%s.webp?v=%s' % (iid, hashlib.md5(rgba.tobytes()).hexdigest()[:6]),
               'url': (info or {}).get('url', ''), 'size': size, 'sizes': sizes, 'color': f.get('colour') or f.get('color') or '',
               'notes': f.get('notes') or f.get('note') or '', 'placeholder': placeholder_used}
        if wishlist:
            rec.update(price=money(f.get('price')) or (info or {}).get('shop_price'),
                       priority='must' if re.match(r'must', f.get('priority', ''), re.I) else 'nice')
            if not f.get('price') and rec['price']:
                notes.append("price %s taken from the shop, in the shop's currency" % rec['price'])
        else:
            rec.update(owned=True, price=money(f.get('paid') or f.get('price')), bought=f.get('bought', ''),
                       store=f.get('from') or f.get('store') or '', photo=measure(rgba, cat), estimated=est)
        by_id[iid] = rec
        report.append((n, 'OK' if not notes else 'CHECK', title, '; '.join(notes)))

    db['items'] = list(by_id.values())
    json.dump(db, open(target, 'w'), indent=1)
    contact_sheet([v for v in by_id.values() if wishlist or v.get('owned')], 'wishlist-report.jpg' if wishlist else 'report.jpg')
    for r in report:
        print('%3s  %-6s %s%s' % (r[0], r[1], r[2][:60], ('  -> ' + r[3]) if r[3] else ''))


def contact_sheet(items, name='report.jpg'):
    """import/report.jpg: every owned piece on one image, for a quick visual check."""
    if not items:
        return
    cols = 6
    S = Image.new('RGB', (cols * 170, ((len(items) + cols - 1) // cols) * 200), 'white')
    d = ImageDraw.Draw(S)
    for k, it in enumerate(items):
        im = Image.open(os.path.join(ROOT, 'docs', it['img'].split('?')[0])).convert('RGBA')
        im.thumbnail((150, 150))
        x, y = (k % cols) * 170, (k // cols) * 200
        bg = Image.new('RGBA', (160, 160), (236, 230, 220, 255))
        bg.alpha_composite(im, ((160 - im.width) // 2, (160 - im.height) // 2))
        S.paste(bg.convert('RGB'), (x + 5, y + 5))
        d.text((x + 6, y + 170), it['name'][:26], fill=(0, 0, 0))
        d.text((x + 6, y + 184), '%s  %s' % (it['cat'], it.get('size') or ''), fill=(120, 110, 100))
    os.makedirs(os.path.join(ROOT, 'import'), exist_ok=True)
    S.save(os.path.join(ROOT, 'import', name), quality=85)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--wishlist']
    wl = '--wishlist' in sys.argv
    main(args[0] if args else os.path.join(ROOT, 'import', 'my-wishlist.txt' if wl else 'my-clothes.txt'), wl)
