const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

/**
 * Build an internal URL that respects the deployment `base` path.
 *
 * The site now serves from the apex of lleg.dev, so `base` is empty and this
 * is currently an identity function. It stays in place deliberately: it is
 * what made moving off the `/techblog` project path a config change rather
 * than a rewrite, and it keeps that true for the next move.
 */
export function withBase(path = '/'): string {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${BASE}${normalized}` || '/';
}

/** Absolute URL, for canonical links, Open Graph tags and the RSS feed. */
export function absoluteUrl(path: string, site: URL | undefined): string {
  return new URL(withBase(path), site ?? 'https://lleg.dev').toString();
}

/** True when `path` is the current page, ignoring trailing slashes. */
export function isActive(path: string, current: string): boolean {
  const strip = (s: string) => s.replace(/\/+$/, '') || '/';
  return strip(withBase(path)) === strip(current);
}
