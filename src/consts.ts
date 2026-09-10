export const SITE = {
  title: "Lleg's study",
  tagline: 'Notes on AI, web, and the systems underneath',
  description:
    'A tech blog by Lleg — deep dives on AI, web engineering, and infrastructure, with diagrams and data instead of hand-waving.',
  author: 'Lleg',
  locale: 'en',
  postsPerPage: 10,
} as const;

export const SOCIALS = [
  { label: 'GitHub', href: 'https://github.com/sehyunnoh' },
  { label: 'LinkedIn', href: 'https://www.linkedin.com/in/devnoh' },
] as const;

/** Set via the UMAMI_WEBSITE_ID env var. Analytics is omitted entirely when unset. */
export const UMAMI_WEBSITE_ID = import.meta.env.UMAMI_WEBSITE_ID ?? '';
export const UMAMI_SCRIPT_URL = 'https://cloud.umami.is/script.js';
