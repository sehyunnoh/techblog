// @ts-check
import { defineConfig, fontProviders } from 'astro/config';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  site: 'https://sehyunnoh.github.io',
  base: '/techblog',
  trailingSlash: 'ignore',
  integrations: [mdx(), sitemap()],
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
