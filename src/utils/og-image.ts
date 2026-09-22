import satori from 'satori';
import { Resvg } from '@resvg/resvg-js';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/**
 * Raw font buffers for satori's own layout engine — separate from the
 * Fontsource files the live site serves via Astro's font pipeline. Satori
 * needs a Buffer on disk at build time, not a subset served over HTTP, so a
 * second copy of Inter lives in devDependencies for this one purpose.
 *
 * Resolved from `process.cwd()` rather than `import.meta.url`: Vite relocates
 * this module into `dist/.prerender/chunks/` during the build, which breaks
 * any path computed relative to the source file's own position. `astro build`
 * always runs from the project root, so cwd is stable regardless of where the
 * bundler puts the compiled chunk.
 */
const FONT_DIR = join(process.cwd(), 'node_modules/@fontsource/inter/files/');
const interRegular = readFileSync(FONT_DIR + 'inter-latin-400-normal.woff');
const interBold = readFileSync(FONT_DIR + 'inter-latin-700-normal.woff');

const WIDTH = 1200;
const HEIGHT = 630;

/** Mirrors :root.dark in src/styles/global.css — a fixed image has one look, and dark reads better in a feed. */
const COLOR = {
  bg: '#0f1115',
  fg: '#e7e9ee',
  fgMuted: '#9aa1af',
  fgFaint: '#6b7280',
  line: '#262b35',
  accent: '#2dd4bf',
  accentFg: '#06231f',
};

export interface OgImageOptions {
  title: string;
  meta?: string;
  tags?: string[];
}

export async function renderOgImage(opts: OgImageOptions): Promise<Buffer> {
  const { title, meta, tags = [] } = opts;

  const svg = await satori(
    {
      type: 'div',
      props: {
        style: {
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          width: WIDTH,
          height: HEIGHT,
          padding: '64px 72px',
          backgroundColor: COLOR.bg,
          fontFamily: 'Inter',
        },
        children: [
          {
            type: 'div',
            props: {
              style: { display: 'flex', alignItems: 'center', gap: 12 },
              children: [
                {
                  type: 'div',
                  props: {
                    style: {
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      width: 34,
                      height: 34,
                      borderRadius: 8,
                      backgroundColor: COLOR.accent,
                      color: COLOR.accentFg,
                      fontSize: 15,
                      fontWeight: 700,
                    },
                    children: 'LL',
                  },
                },
                {
                  type: 'div',
                  props: {
                    style: { display: 'flex', fontSize: 20, fontWeight: 700, color: COLOR.fg },
                    children: "Lleg's study",
                  },
                },
              ],
            },
          },
          {
            type: 'div',
            props: {
              style: {
                display: 'flex',
                fontSize: title.length > 55 ? 46 : 54,
                fontWeight: 700,
                color: COLOR.fg,
                lineHeight: 1.2,
                letterSpacing: -1,
              },
              children: title,
            },
          },
          {
            type: 'div',
            props: {
              style: { display: 'flex', flexDirection: 'column', gap: 18 },
              children: [
                ...(tags.length > 0
                  ? [
                      {
                        type: 'div',
                        props: {
                          style: { display: 'flex', gap: 10, flexWrap: 'wrap' },
                          children: tags.slice(0, 5).map((t) => ({
                            type: 'div',
                            props: {
                              style: {
                                display: 'flex',
                                fontSize: 16,
                                color: COLOR.fgMuted,
                                border: `1px solid ${COLOR.line}`,
                                borderRadius: 999,
                                padding: '6px 16px',
                              },
                              children: `#${t}`,
                            },
                          })),
                        },
                      },
                    ]
                  : []),
                {
                  type: 'div',
                  props: {
                    style: {
                      display: 'flex',
                      fontSize: 17,
                      color: COLOR.fgFaint,
                      borderTop: `1px solid ${COLOR.line}`,
                      paddingTop: 18,
                    },
                    children: meta ?? 'lleg.dev',
                  },
                },
              ],
            },
          },
        ],
      },
    },
    {
      width: WIDTH,
      height: HEIGHT,
      fonts: [
        { name: 'Inter', data: interRegular, weight: 400, style: 'normal' },
        { name: 'Inter', data: interBold, weight: 700, style: 'normal' },
      ],
    }
  );

  const resvg = new Resvg(svg, { fitTo: { mode: 'width', value: WIDTH } });
  return resvg.render().asPng();
}
