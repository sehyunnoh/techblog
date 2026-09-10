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

export const collections = { blog };
