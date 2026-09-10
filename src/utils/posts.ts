import { getCollection, type CollectionEntry } from 'astro:content';

export type Post = CollectionEntry<'blog'>;

/**
 * Published posts, newest first.
 *
 * Drafts are visible while running `astro dev` and dropped from production
 * builds, so a work-in-progress can be previewed without ever shipping.
 */
export async function getPublishedPosts(): Promise<Post[]> {
  const posts = await getCollection('blog', ({ data }) => import.meta.env.DEV || !data.draft);
  return posts.sort((a, b) => b.data.pubDate.getTime() - a.data.pubDate.getTime());
}

/** Tag ids used by at least one published post, ordered by frequency then name. */
export async function getTagCounts(): Promise<{ tag: string; count: number }[]> {
  const posts = await getPublishedPosts();
  const counts = new Map<string, number>();
  for (const post of posts) {
    for (const tag of post.data.tags) {
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag));
}

export async function getPostsByTag(tag: string): Promise<Post[]> {
  const posts = await getPublishedPosts();
  return posts.filter((p) => p.data.tags.includes(tag as never));
}

/**
 * Reading time in minutes, from the raw source.
 *
 * Fenced code and JSX component blocks are stripped first: a 60-line config
 * dump is scanned, not read, and counting it as prose inflates the estimate.
 */
export function readingTime(body: string | undefined): number {
  if (!body) return 1;
  const prose = body
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/<[A-Z][\s\S]*?\/>/g, ' ')
    .replace(/<[^>]+>/g, ' ');
  const words = prose.split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(words / 220));
}

/** Word count of the prose, used to keep posts inside the target length. */
export function wordCount(body: string | undefined): number {
  if (!body) return 0;
  return body
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/<[^>]+>/g, ' ')
    .split(/\s+/)
    .filter(Boolean).length;
}

const DATE_FMT = new Intl.DateTimeFormat('en-US', {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  timeZone: 'UTC',
});

export function formatDate(date: Date): string {
  return DATE_FMT.format(date);
}

export function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/**
 * Posts sharing the most tags with `post`, for the "keep reading" list.
 * Ties break toward the newer post.
 */
export function relatedPosts(post: Post, all: Post[], limit = 3): Post[] {
  const tags = new Set<string>(post.data.tags);
  return all
    .filter((p) => p.id !== post.id)
    .map((p) => ({ p, shared: p.data.tags.filter((t) => tags.has(t)).length }))
    .filter((x) => x.shared > 0)
    .sort((a, b) => b.shared - a.shared || b.p.data.pubDate.getTime() - a.p.data.pubDate.getTime())
    .slice(0, limit)
    .map((x) => x.p);
}
