import type { APIRoute, GetStaticPaths } from 'astro';
import { getPublishedPosts, formatDate, readingTime } from '../../utils/posts';
import { tagLabel } from '../../tags';
import { renderOgImage } from '../../utils/og-image';

export const getStaticPaths: GetStaticPaths = async () => {
  const posts = await getPublishedPosts();
  return posts.map((post) => ({
    params: { slug: post.id },
    props: { post },
  }));
};

export const GET: APIRoute = async ({ props }) => {
  const { post } = props as { post: Awaited<ReturnType<typeof getPublishedPosts>>[number] };
  const minutes = readingTime(post.body);
  const png = await renderOgImage({
    title: post.data.title,
    meta: `${formatDate(post.data.pubDate)} · ${minutes} min read`,
    tags: post.data.tags.map(tagLabel),
  });
  return new Response(new Uint8Array(png), {
    headers: { 'Content-Type': 'image/png' },
  });
};
