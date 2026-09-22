import type { APIRoute } from 'astro';
import { SITE } from '../consts';
import { renderOgImage } from '../utils/og-image';

export const GET: APIRoute = async () => {
  const png = await renderOgImage({
    title: SITE.tagline,
    meta: 'lleg.dev',
  });
  return new Response(new Uint8Array(png), {
    headers: { 'Content-Type': 'image/png' },
  });
};
