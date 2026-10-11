import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import { SITE } from '../../consts';
import { withBase } from '../../utils/url';
import { getPublishedGuides } from '../../utils/guides';

/**
 * Guides are revised in place, so each item is dated by its last update, not
 * its first publication. A feed reader then resurfaces a guide that changed.
 */
export async function GET(context: APIContext) {
  const guides = (await getPublishedGuides()).filter((g) => !g.data.draft);

  return rss({
    title: `${SITE.title} · Guides`,
    description: "Reference guides from Lleg's study: explainers and how-tos, revised in place.",
    site: context.site!,
    trailingSlash: false,
    items: guides.map((guide) => ({
      title: guide.data.title,
      description: guide.data.description,
      pubDate: guide.data.updatedDate ?? guide.data.pubDate,
      link: withBase(`/guides/${guide.id}`),
      categories: [...guide.data.tags],
      author: SITE.author,
    })),
    customData: `<language>en-us</language>`,
  });
}
