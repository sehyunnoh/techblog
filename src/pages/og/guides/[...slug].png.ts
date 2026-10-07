import type { APIRoute, GetStaticPaths } from 'astro';
import { getPublishedGuides, formatDate, readingTime } from '../../../utils/guides';
import { tagLabel } from '../../../tags';
import { renderOgImage } from '../../../utils/og-image';

export const getStaticPaths: GetStaticPaths = async () => {
  const guides = await getPublishedGuides();
  return guides.map((guide) => ({
    params: { slug: guide.id },
    props: { guide },
  }));
};

export const GET: APIRoute = async ({ props }) => {
  const { guide } = props as { guide: Awaited<ReturnType<typeof getPublishedGuides>>[number] };
  const minutes = readingTime(guide.body);
  const png = await renderOgImage({
    title: guide.data.title,
    meta: `Guide · ${formatDate(guide.data.pubDate)} · ${minutes} min read`,
    tags: guide.data.tags.map(tagLabel),
  });
  return new Response(new Uint8Array(png), {
    headers: { 'Content-Type': 'image/png' },
  });
};
