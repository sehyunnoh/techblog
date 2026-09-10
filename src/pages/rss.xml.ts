import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import { SITE } from '../consts';
import { withBase } from '../utils/url';
import { getPublishedPosts } from '../utils/posts';

export async function GET(context: APIContext) {
  const posts = (await getPublishedPosts()).filter((p) => !p.data.draft);

  return rss({
    title: SITE.title,
    description: SITE.description,
    site: context.site!,
    trailingSlash: false,
    items: posts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      pubDate: post.data.pubDate,
      link: withBase(`/posts/${post.id}`),
      categories: [...post.data.tags],
      author: SITE.author,
    })),
    customData: `<language>en-us</language>`,
  });
}
