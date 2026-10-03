Files starting with `_` are excluded from the `guides` collection by its glob
pattern (see `src/content.config.ts`), the same convention the `blog`
collection uses. This file exists only so the directory is tracked by git and
to leave a note for whoever (human or Claude) adds the first real guide.

## What belongs here

Reference material: explainers and "how do I actually use this" write-ups.
Unlike `src/content/blog`, entries here are not tied to a news hook, do not
compete for the one-post-per-day slot, and are expected to be revised in
place as the thing they explain changes (bump `updatedDate` when you do).

## What still applies from the Posts editorial rules

- No em dashes.
- Write like a human: vary sentence rhythm, avoid formulaic transitions, reread
  specifically checking for AI-writing tells before publishing.
- Every non-obvious claim still needs a real, checkable source.
- English prose, Korean conversation with the site owner, same as Posts.

## What does not apply here

- No 1,500-2,500 word target and no mandatory
  hook/background/sections/trade-offs/takeaways/references structure. A guide
  can be as short as the topic needs.
- No one-per-day cap.
- Figure/Chart/Mermaid visuals are encouraged when they clarify a mechanism,
  not required on every entry the way they are on Posts.
- No OG-image generation per entry (falls back to the site's default OG
  image) and guides are not included in `rss.xml`. Both can be added later
  if that stops being the right call.
