# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Astro-based blog ("Lleg's study", deployed at `https://lleg.dev`) whose posts are researched and written by Claude, one at a time, in Korean-language sessions with the site owner. The posts themselves are always in English. See "Editorial rules" below — the file those rules live in (`requirements.md`) is gitignored and will not exist in a fresh clone, so this summary is the only copy that travels with the repo.

## Commands

```
npm run dev       # astro dev, local server
npm run build     # astro build, then `pagefind --site dist` to build the search index
npm run preview   # serve the built dist/ locally
npm run check     # astro check (type-checks .astro/.mdx against src/content.config.ts)
```

There is no lint script and no test runner in this repo. Before publishing a post, run `npm run check` and `npm run build`, then actually load the page in a browser in both light and dark theme, not just once either has passed — several past defects (a chart plugin bleeding across chart types, a clipped chart label, Mermaid anchors shifting after client-side render, doubled smart quotes) only showed up visually and passed both `check` and `build` cleanly.

## Content architecture

- Two content collections, both defined in `src/content.config.ts`: `blog` (Posts) and `guides` (Guides, added 2026-10-03). Both load from their own directory (`src/content/blog/**/*.{md,mdx}` and `src/content/guides/**/*.{md,mdx}`, glob loader, files starting with `_` excluded) and share a near-identical schema: `title` (≤90 chars), `description` (40–200 chars), `pubDate`, optional `updatedDate`, `tags` (1–6 entries), `draft` (default `false`). `blog` additionally has an optional `heroAlt`; `guides` does not.
- **Posts vs Guides**: Posts are the news-reactive deep dives this file's "Editorial rules" section describes — one per day, tied to something that just happened, built around a measured reversal. Guides (`/guides`, nav link in `src/components/Header.astro`) are reference material: explainers and how-tos with no daily cap and no news hook, meant to be revised in place over time (bump `updatedDate` when you do). See `src/content/guides/_about.md` for the exact rule set that does and doesn't carry over from Posts. Both collections share the same controlled tag vocabulary (`src/tags.ts`) and the `/tags` index/`/tags/[tag]` pages merge counts and listings across both, each under its own "Posts"/"Guides" heading when a tag has both. Guides currently do not appear in `rss.xml`, do not get a per-entry OG image (they fall back to the site default), and are not listed on the homepage — those were deliberate v1 scope cuts, not oversights, and can be revisited.
- Shared date/reading-time/word-count helpers live in `src/utils/content.ts`; `src/utils/posts.ts` and `src/utils/guides.ts` each re-export them and add their own collection-specific queries (`getPublishedPosts`/`getPublishedGuides`, `relatedPosts`/`relatedGuides`, etc.). `PostCard.astro` renders either kind of entry — pass `kind="guide"` when rendering a guide, it defaults to `"post"`.
- `tags` is a controlled vocabulary, not free text: valid ids are the keys of `TAGS` in `src/tags.ts` (grouped as Domain / Technology / Format), and anything outside that list fails the build. Add a tag there before using it in a post.
- Draft posts (`draft: true`) render in `astro dev` but are excluded from production builds and RSS — see `getPublishedPosts()` in `src/utils/posts.ts`, which every listing page, the tag pages, `rss.xml.ts` and the OG-image route all go through rather than querying the collection directly.
- Internal links and asset paths should go through `withBase()` / `absoluteUrl()` in `src/utils/url.ts` instead of being hardcoded. `base` is currently empty (the site serves from the apex), so this is presently an identity function, but it is what made a past `/techblog` → apex migration a one-line config change instead of a rewrite.

## Visual components

Every post is expected to carry real visuals (see "Editorial rules"), built from three components in `src/components/`:

- `Figure.astro` — the shared frame every visual sits in. `caption` is required; a visual that can't be captioned in one sentence usually shouldn't exist.
- `Chart.astro` — a Chart.js wrapper (`type: bar | line | area`, `labels`, `series`, `format: plain | compact | usd | percent | bytes`, optional `logY` for data spanning orders of magnitude). Only build a chart when there's real measured data behind it.
- `Mermaid.astro` — renders client-side (dynamically imported, so the diagram library is only fetched on pages that use it) rather than at build time, specifically so it can redraw when the reader flips the theme toggle; a build-time-rendered diagram would bake in one palette.

Theme switching is a `.dark` class Astro/`ThemeToggle.astro` toggles on `<html>` (see `src/styles/global.css`), not a `prefers-color-scheme` media query alone. Any inline SVG written directly into a post must use the CSS custom properties already defined there (`--fg`, `--fg-muted`, `--bg-subtle`, `--line`, `--series-1` through `--series-8`, `--accent`, …) rather than hardcoded hex colors, or it will only look right in one theme.

## Other build-time generation

- **OG images** are generated per post automatically at build time (`src/pages/og/[...slug].png.ts` + `src/utils/og-image.ts`, Satori → resvg) from the post's title/date/reading time/tags. There is no per-post image asset to create or maintain.
- **Search** is Pagefind, built as a second step after `astro build` (see the `build` script above); its index lives in `dist/pagefind` and is not something `astro dev` serves.
- **Fonts** (Inter, JetBrains Mono) are self-hosted via Astro's Fonts API (`fontProviders.fontsource()` in `astro.config.mjs`) rather than pulled from a font CDN at request time.

## Editorial rules for writing posts

(Condensed from `requirements.md`, which is gitignored — the full version only exists on the machine that already has it.)

- Posts are written in **English**; conversation with the site owner is in Korean.
- **One post per day, maximum.** If a second one is ready the same day, queue it for the next day rather than publishing both — the stated reason is that a burst of same-day deep-dives reads as automated, and the blog's asset is trust that claims were actually checked.
- Every claim needs a real, checkable source: official docs, release notes, source code, a paper, or a measurement taken directly (and stated as such, with methodology). No hallucinated links.
- Standard structure: hook/problem → minimal background → 3–5 core sections, each with at least one visual → trade-offs/pitfalls → 3–5 takeaway bullets → numbered references.
- Target length 1,500–2,500 words. Tone is practical and specific; no marketing language, and trade-offs must be stated, not glossed over.
- Visuals: Mermaid for flows/sequences/architecture, inline SVG for comparisons Mermaid can't express, Chart.js only when there's real data behind it — never a chart built to hit a visual-count quota.
- **No em dashes anywhere in post content** (title, description, body, captions, alt text) — restructure with a comma, period, or parenthetical instead. This is a standing style rule the repo owner has asked for explicitly; it does not apply retroactively to posts already published.
- Write post prose so it reads as human-written, not AI-generated: vary sentence rhythm, avoid formulaic transitions and repeated rule-of-three list patterns, and reread a draft specifically checking for these before publishing. Also not retroactive.
- Before publishing: `npm run check`, `npm run build`, and a real browser check in both themes (see Commands above), then commit and push directly — publishing is understood to be included in "write this post" unless the user says otherwise.

## Local-only files

`requirements.md` (the full editorial/workflow spec this section summarizes) and `topics.md` (a running backlog of researched-but-unwritten post topics, complete with sources and sometimes original measurements already taken) are both gitignored. They exist on the machine this project is normally worked from but will be absent from a fresh clone or a different machine — check for them before assuming they don't apply.
