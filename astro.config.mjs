// @ts-check
import { readFileSync, readdirSync } from 'node:fs';
import { defineConfig, fontProviders } from 'astro/config';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

/**
 * Maps each post/guide's route to a `lastmod` date (its `updatedDate` if it
 * has one, else `pubDate`), read straight from frontmatter rather than
 * through `astro:content` — that virtual module isn't reliably resolvable
 * from this file's module graph, while plain `fs` always is. Only posts and
 * guides carry a meaningful date; every other route is left for the sitemap
 * integration to stamp with the build date, its own default.
 */
function loadLastmods() {
  const map = new Map();
  const sources = [
    ['src/content/blog', '/posts/'],
    ['src/content/guides', '/guides/'],
  ];
  for (const [dir, routePrefix] of sources) {
    for (const file of readdirSync(dir)) {
      if (file.startsWith('_') || !/\.mdx?$/.test(file)) continue;
      const raw = readFileSync(`${dir}/${file}`, 'utf-8');
      const frontmatter = raw.match(/^---\n([\s\S]*?)\n---/)?.[1];
      if (!frontmatter || /draft:\s*true/.test(frontmatter)) continue;
      const date =
        frontmatter.match(/updatedDate:\s*['"]?([\d-]+)/)?.[1] ??
        frontmatter.match(/pubDate:\s*['"]?([\d-]+)/)?.[1];
      if (!date) continue;
      const slug = file.replace(/\.mdx?$/, '');
      map.set(`${routePrefix}${slug}/`, date);
    }
  }
  return map;
}

const lastmods = loadLastmods();

export default defineConfig({
  site: 'https://lleg.dev',
  trailingSlash: 'ignore',
  integrations: [
    mdx(),
    sitemap({
      // Keep noindex pages out of the sitemap. Listing a page and then telling
      // Google not to index it is not harmful, but it reports as "Excluded by
      // noindex tag" in Search Console — a warning-shaped line for a page that
      // is behaving exactly as intended.
      filter: (page) => !new URL(page).pathname.startsWith('/search'),
      serialize(item) {
        const lastmod = lastmods.get(new URL(item.url).pathname);
        return lastmod ? { ...item, lastmod } : item;
      },
    }),
  ],
  /*
   * Fonts are downloaded at build time and served from this origin. Readers
   * never contact a font CDN, so no visitor IP leaves the site to fetch a
   * typeface. Fontsource rather than the Google provider keeps Google out of
   * the build too.
   *
   * The weights are a variable range, not a list: the design uses 550, 620,
   * 640, 650, 680 and 690, which only render on a variable font. Discrete
   * weights would silently snap them to the nearest 100.
   */
  fonts: [
    {
      name: 'Inter',
      cssVariable: '--font-inter',
      provider: fontProviders.fontsource(),
      weights: ['400 700'],
      styles: ['normal'],
      subsets: ['latin'],
      fallbacks: ['ui-sans-serif', 'system-ui', 'sans-serif'],
    },
    {
      name: 'JetBrains Mono',
      cssVariable: '--font-jetbrains-mono',
      provider: fontProviders.fontsource(),
      weights: [400, 500],
      styles: ['normal'],
      subsets: ['latin'],
      fallbacks: ['ui-monospace', 'monospace'],
    },
  ],
  markdown: {
    shikiConfig: {
      themes: { light: 'github-light', dark: 'github-dark-dimmed' },
      wrap: false,
    },
  },
  vite: {
    plugins: [tailwindcss()],
  },
});
