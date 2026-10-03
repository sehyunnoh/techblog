import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';
import { TAG_IDS } from './tags';

const blog = defineCollection({
  loader: glob({ base: './src/content/blog', pattern: '**/[^_]*.{md,mdx}' }),
  schema: z.object({
    title: z.string().max(90),
    description: z.string().min(40).max(200),
    pubDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    // Restricted to the controlled vocabulary in src/tags.ts.
    tags: z.array(z.enum(TAG_IDS)).min(1).max(6),
    heroAlt: z.string().optional(),
    draft: z.boolean().default(false),
  }),
});

/**
 * Reference material: explainers and how-tos, not tied to a news hook or the
 * blog's one-per-day cadence. `updatedDate` matters more here than on a post —
 * a guide is expected to get revised in place as the thing it explains changes.
 */
const guides = defineCollection({
  loader: glob({ base: './src/content/guides', pattern: '**/[^_]*.{md,mdx}' }),
  schema: z.object({
    title: z.string().max(90),
    description: z.string().min(40).max(200),
    pubDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    tags: z.array(z.enum(TAG_IDS)).min(1).max(6),
    draft: z.boolean().default(false),
  }),
});

export const collections = { blog, guides };
