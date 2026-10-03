import { getCollection, type CollectionEntry } from 'astro:content';

export { formatDate, isoDate, readingTime, wordCount } from './content';

export type Guide = CollectionEntry<'guides'>;

/**
 * Published guides, newest first.
 *
 * Drafts are visible while running `astro dev` and dropped from production
 * builds, so a work-in-progress can be previewed without ever shipping.
 */
export async function getPublishedGuides(): Promise<Guide[]> {
  const guides = await getCollection('guides', ({ data }) => import.meta.env.DEV || !data.draft);
  return guides.sort((a, b) => b.data.pubDate.getTime() - a.data.pubDate.getTime());
}

export async function getGuidesByTag(tag: string): Promise<Guide[]> {
  const guides = await getPublishedGuides();
  return guides.filter((g) => g.data.tags.includes(tag as never));
}

/**
 * Guides sharing the most tags with `guide`, for the "keep reading" list.
 * Ties break toward the newer guide.
 */
export function relatedGuides(guide: Guide, all: Guide[], limit = 3): Guide[] {
  const tags = new Set<string>(guide.data.tags);
  return all
    .filter((g) => g.id !== guide.id)
    .map((g) => ({ g, shared: g.data.tags.filter((t) => tags.has(t)).length }))
    .filter((x) => x.shared > 0)
    .sort((a, b) => b.shared - a.shared || b.g.data.pubDate.getTime() - a.g.data.pubDate.getTime())
    .slice(0, limit)
    .map((x) => x.g);
}
