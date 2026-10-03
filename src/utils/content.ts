import type { CollectionEntry } from 'astro:content';

/** Any published entry, from either the blog or the guides collection. */
export type ContentEntry = CollectionEntry<'blog'> | CollectionEntry<'guides'>;

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
