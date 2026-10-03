# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One person: the owner (Mateusz), using it on his Android phone as an installed web app. Interested in menswear with a vintage, workwear and ivy leaning (Timecatcher, G.H.Bass Weejuns, selvedge denim). Not a designer or developer. Uses it mostly while getting dressed in the morning (quick: pick or log today's outfit) and in relaxed moments in the evening (organising the closet, planning outfits, thinking about what to buy).

## Product Purpose

A personal closet manager, in the spirit of Indyx. In order of importance:

1. Plan outfits: put looks together from pieces he owns and plan which day to wear them.
2. Know the closet: every piece in one place with its photo, size, measurements, price and details.
3. Shopping and wishlist: keep track of what he wants and decide what to buy next, informed by what he already owns.

Cost per wear and wear tracking support these jobs; they are not the headline.

## Positioning

A private, free, single-user closet that lives on his own phone: no account, no ads, no social feed, works offline. Pieces arrive with clean cut-out shop photos and real size-chart measurements, because Claude imports them from shop links, order emails or descriptions and publishes them as app updates.

## Operating Context

- Installed from https://matjan00.github.io/wardrobe-app/ to the Android home screen; opened one-handed.
- Morning use is quick and task-focused; evening use is browsing and planning.
- New pieces mostly come in through Claude (links, order emails, descriptions → import tool → "Update available" in the app). He can also add and edit everything on the phone, including his own photos.
- Prices are in złoty.

## Capabilities and Constraints

- Tabs: Closet, Outfits (with builder), Plan (calendar), Wishlist, Insights.
- Outfit picture: real product cut-outs stacked or in a flat lay. No avatar, mannequin or body figure (tried and rejected). No AI try-on (tried, results looked bad).
- Single static HTML file in `docs/`, vanilla JS, no build step, hosted on GitHub Pages. Data in localStorage, own photos in IndexedDB, offline via service worker. Every release goes through `node tools/release.cjs "note"` so the phone shows an update notice.
- Everything must stay free to run.
- No sync between devices; backups are exported files.

## Brand Commitments

- Name: Wardrobe.
- Language: English.
- Voice: plain, friendly, short. The owner is not technical, so no jargon.

## Evidence on Hand

Real pieces in `docs/data/items.json` with photos in `docs/img/` (Timecatcher trousers, jacket, jeans and five T-shirts; G.H.Bass and Zara loafers). No testimonials or usage data; none should be invented.

## Product Principles

1. Getting dressed comes first: the most common morning actions take one or two taps.
2. His real clothes, shown honestly: real photos and real measurements over illustrations or guesses.
3. Private and his own: no accounts, nothing leaves the phone except backups he exports.
4. Every piece is fully editable on the phone.
5. Calm and uncluttered: an organising tool, not a shop.
