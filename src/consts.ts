export const SITE = {
  title: "Lleg's study",
  tagline: 'Notes on AI, web, and the systems underneath',
  description:
    'A tech blog by Lleg. Deep dives on AI, web engineering and infrastructure, with diagrams and measured numbers.',
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

/**
 * Whether the site serves Google AdSense ads. The privacy page switches
 * between two accurate texts on this flag, so the disclosure never says
 * something the site is not doing.
 *
 * Turning this on is not enough by itself: before it goes live the site also
 * needs the ad script and a Google-certified consent banner for visitors in
 * the EEA, the UK and Switzerland. Nothing in this repo loads ads yet.
 */
export const ADS_ENABLED = false;
