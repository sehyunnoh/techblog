/**
 * Controlled tag vocabulary.
 *
 * Posts may only use tags declared here — the content schema rejects anything
 * else at build time. This keeps the tag index from degenerating into a long
 * tail of near-duplicates ("k8s" vs "kubernetes" vs "Kubernetes").
 *
 * To introduce a tag, add it below with a label and a one-line description.
 */
export const TAGS = {
  // ---- Domain -------------------------------------------------------------
  ai: { label: 'AI', group: 'Domain', description: 'Machine learning systems and the engineering around them.' },
  llm: { label: 'LLM', group: 'Domain', description: 'Large language models, prompting, agents and evaluation.' },
  web: { label: 'Web', group: 'Domain', description: 'The browser platform, standards and web performance.' },
  frontend: { label: 'Frontend', group: 'Domain', description: 'UI architecture, rendering strategies and tooling.' },
  backend: { label: 'Backend', group: 'Domain', description: 'APIs, services and the data layer behind them.' },
  devops: { label: 'DevOps', group: 'Domain', description: 'Delivery pipelines, infrastructure and operations.' },
  observability: { label: 'Observability', group: 'Domain', description: 'Metrics, traces, logs and everything they cost.' },
  data: { label: 'Data', group: 'Domain', description: 'Storage engines, pipelines and query performance.' },
  security: { label: 'Security', group: 'Domain', description: 'Threat models, hardening and secure defaults.' },

  // ---- Technology ---------------------------------------------------------
  python: { label: 'Python', group: 'Technology', description: 'The Python ecosystem.' },
  typescript: { label: 'TypeScript', group: 'Technology', description: 'TypeScript and the JavaScript runtime it compiles to.' },
  rust: { label: 'Rust', group: 'Technology', description: 'The Rust language and its ecosystem.' },
  go: { label: 'Go', group: 'Technology', description: 'The Go language and its ecosystem.' },
  react: { label: 'React', group: 'Technology', description: 'React and its rendering model.' },
  docker: { label: 'Docker', group: 'Technology', description: 'Container images and runtimes.' },
  kubernetes: { label: 'Kubernetes', group: 'Technology', description: 'Kubernetes and the operators around it.' },
  postgres: { label: 'Postgres', group: 'Technology', description: 'PostgreSQL internals and operations.' },
  prometheus: { label: 'Prometheus', group: 'Technology', description: 'Prometheus, PromQL and its storage engine.' },
  opentelemetry: { label: 'OpenTelemetry', group: 'Technology', description: 'The OpenTelemetry standard, SDKs and Collector.' },

  // ---- Format -------------------------------------------------------------
  tutorial: { label: 'Tutorial', group: 'Format', description: 'Step-by-step, follow-along walkthroughs.' },
  'deep-dive': { label: 'Deep dive', group: 'Format', description: 'Long-form analysis of how something actually works.' },
  benchmark: { label: 'Benchmark', group: 'Format', description: 'Measured comparisons with reproducible numbers.' },
  architecture: { label: 'Architecture', group: 'Format', description: 'System design, trade-offs and failure modes.' },
  'cost-engineering': { label: 'Cost engineering', group: 'Format', description: 'Making systems cheaper without making them worse.' },
  opinion: { label: 'Opinion', group: 'Format', description: 'Arguments, not neutral surveys.' },
} as const;

export type Tag = keyof typeof TAGS;

export const TAG_IDS = Object.keys(TAGS) as [Tag, ...Tag[]];

export const TAG_GROUPS = ['Domain', 'Technology', 'Format'] as const;

export function tagLabel(id: string): string {
  return TAGS[id as Tag]?.label ?? id;
}

export function tagDescription(id: string): string {
  return TAGS[id as Tag]?.description ?? '';
}

export function tagGroup(id: string): string {
  return TAGS[id as Tag]?.group ?? 'Other';
}
