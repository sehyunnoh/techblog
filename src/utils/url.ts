const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

/**
 * Build an internal URL that respects the deployment `base` path.
 *
 * The site is served from a project repository (`/techblog`), so hard-coded
 * absolute paths such as `/posts/foo` resolve to a 404 in production while
 * still working in `astro dev`. Every internal href and asset path must go
 * through this helper.
 */
export function withBase(path = '/'): string {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${BASE}${normalized}` || '/';
}

/** Absolute URL, for canonical links, Open Graph tags and the RSS feed. */
export function absoluteUrl(path: string, site: URL | undefined): string {
  return new URL(withBase(path), site ?? 'https://sehyunnoh.github.io').toString();
}

/** True when `path` is the current page, ignoring trailing slashes. */
export function isActive(path: string, current: string): boolean {
  const strip = (s: string) => s.replace(/\/+$/, '') || '/';
  return strip(withBase(path)) === strip(current);
}
