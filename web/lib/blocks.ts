/* Blog Visual Engine — block types and API client.

   Mirrors api/app/blog_engine/schema.py. The server is the validator; these
   types exist so the editor can build blocks without guessing shapes, and so
   a wrong attr is a compile error here before it is a 422 there. */
import api from './api';

export type MarkType =
  | 'bold' | 'italic' | 'underline' | 'strike' | 'code' | 'link'
  | 'highlight' | 'emphasis' | 'sup' | 'sub';
export type HighlightToken = 'amber' | 'mint' | 'sky' | 'rose';
export type EmphasisToken = 'brand' | 'accent' | 'positive' | 'warning';

export interface Mark {
  type: MarkType;
  attrs?: Record<string, string>;
}
export interface Run {
  text: string;
  marks?: Mark[];
}
export type RichText = Run[];

export interface ImageAttrs {
  asset_id?: string | null;
  src: string;
  alt: string;
  caption?: string | null;
  credit?: string | null;
  width: number;
  height: number;
  layout?: 'inset' | 'full' | 'breakout';
  priority?: boolean;
  link?: string | null;
  variants?: { src: string; width: number; format?: string }[];
  lqip?: string | null;
}

export type BlockType =
  | 'paragraph' | 'heading' | 'key_takeaways' | 'list' | 'steps' | 'image'
  | 'gallery' | 'compare_slider' | 'video' | 'table' | 'callout' | 'quote'
  | 'code' | 'stat_band' | 'chart' | 'process_flow' | 'faq' | 'cta'
  | 'divider' | 'embed' | 'legacy_html';

/* Loose on purpose: attrs/content vary by type and the server validates. */
export interface Block {
  id: string;
  type: BlockType;
  version?: number;
  attrs?: Record<string, any>;
  content?: any;
}

export const BLOCK_TYPES: { type: BlockType; label: string; hint: string; visual: boolean }[] = [
  { type: 'paragraph', label: 'Paragraph', hint: 'Body text', visual: false },
  { type: 'heading', label: 'Heading', hint: 'Section title (H2/H3/H4)', visual: false },
  { type: 'key_takeaways', label: 'Key takeaways', hint: '3–5 bullets near the top', visual: false },
  { type: 'list', label: 'List', hint: 'Bullets, numbers or checklist', visual: false },
  { type: 'steps', label: 'Steps', hint: 'Numbered how-to (HowTo schema)', visual: true },
  { type: 'image', label: 'Image', hint: 'Figure with caption', visual: true },
  { type: 'gallery', label: 'Gallery', hint: '2–4 images in a grid', visual: true },
  { type: 'compare_slider', label: 'Before / after', hint: 'Two images, drag to compare', visual: true },
  { type: 'video', label: 'Video', hint: 'YouTube or self-hosted clip', visual: true },
  { type: 'table', label: 'Table', hint: 'Rows and columns with a caption', visual: true },
  { type: 'callout', label: 'Callout', hint: 'Note, tip, warning or result', visual: true },
  { type: 'quote', label: 'Quote', hint: 'Pull quote with attribution', visual: true },
  { type: 'code', label: 'Code', hint: 'Code with a language label', visual: true },
  { type: 'stat_band', label: 'Stat band', hint: '2–4 big numbers', visual: true },
  { type: 'chart', label: 'Chart', hint: 'Bar, line or donut from a table', visual: true },
  { type: 'process_flow', label: 'Process flow', hint: 'Left-to-right pipeline', visual: true },
  { type: 'faq', label: 'FAQ', hint: 'Questions and answers (FAQ schema)', visual: false },
  { type: 'cta', label: 'Call to action', hint: 'Link to a service or booking', visual: false },
  { type: 'divider', label: 'Divider', hint: 'Section break', visual: false },
  { type: 'embed', label: 'Embed', hint: 'LinkedIn or X post (link card)', visual: false },
];

export function newBlockId(): string {
  const bytes = new Uint8Array(4);
  crypto.getRandomValues(bytes);
  return 'blk_' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

const PLACEHOLDER_IMG = (): ImageAttrs => ({ src: '', alt: '', width: 1600, height: 900, layout: 'inset' });

/* A sensible empty block of each type — enough to pass the schema once the
   writer fills the required fields. */
export function newBlock(type: BlockType): Block {
  const id = newBlockId();
  switch (type) {
    case 'paragraph': return { id, type, attrs: { variant: 'normal' }, content: [{ text: '' }] };
    case 'heading': return { id, type, attrs: { level: 2, gradient: false }, content: [{ text: '' }] };
    case 'key_takeaways': return { id, type, attrs: { title: 'Key takeaways' }, content: [[{ text: '' }], [{ text: '' }], [{ text: '' }]] };
    case 'list': return { id, type, attrs: { style: 'bullet' }, content: [{ content: [{ text: '' }], checked: false }] };
    case 'steps': return { id, type, attrs: { title: null, total_time: null }, content: [{ title: [{ text: '' }], body: [] }, { title: [{ text: '' }], body: [] }] };
    case 'image': return { id, type, attrs: PLACEHOLDER_IMG() };
    case 'gallery': return { id, type, attrs: { layout: 'breakout', caption: null }, content: [PLACEHOLDER_IMG(), PLACEHOLDER_IMG()] };
    case 'compare_slider': return { id, type, attrs: { before: PLACEHOLDER_IMG(), after: PLACEHOLDER_IMG(), label_before: 'Before', label_after: 'After', layout: 'breakout', caption: null } };
    case 'video': return { id, type, attrs: { kind: 'youtube', youtube_id: '', src: null, poster: '', title: '', description: '', upload_date: new Date().toISOString().slice(0, 10), duration: 'PT1M', width: 1280, height: 720, loop: false, layout: 'inset', caption: null } };
    case 'table': return { id, type, attrs: { caption: '', has_header: true, align: ['left', 'left'], sortable: false, mobile: 'scroll', layout: 'inset' }, content: [[[{ text: 'Column' }], [{ text: 'Column' }]], [[{ text: '' }], [{ text: '' }]]] };
    case 'callout': return { id, type, attrs: { kind: 'tip', title: null }, content: [{ text: '' }] };
    case 'quote': return { id, type, attrs: { attribution: '', role: null, company: null }, content: [{ text: '' }] };
    case 'code': return { id, type, attrs: { language: 'text', caption: null }, content: '' };
    case 'stat_band': return { id, type, attrs: {}, content: [{ value: '', label: '', numeric: null, prefix: '', suffix: '' }, { value: '', label: '', numeric: null, prefix: '', suffix: '' }] };
    case 'chart': return { id, type, attrs: { kind: 'bar', title: '', unit: '', labels: ['A', 'B', 'C'], series: [{ name: 'Series', values: [0, 0, 0] }], layout: 'inset', source: null } };
    case 'process_flow': return { id, type, attrs: { title: null, layout: 'breakout' }, content: [{ label: 'Start', sub: null, kind: 'system' }, { label: 'Bot', sub: null, kind: 'bot' }, { label: 'Done', sub: null, kind: 'result' }] };
    case 'faq': return { id, type, attrs: { title: 'Frequently asked questions' }, content: [{ question: '', answer: [{ text: '' }] }] };
    case 'cta': return { id, type, attrs: { heading: '', text: null, button_label: 'Book the free audit', href: 'https://calendly.com/agenticaiautomation', kind: 'calendly' } };
    case 'divider': return { id, type, attrs: { style: 'line' } };
    case 'embed': return { id, type, attrs: { provider: 'linkedin', url: '', title: null, preview_text: null } };
    case 'legacy_html': return { id, type, attrs: { html: '', source: 'html' } };
  }
}

export function plainText(runs: RichText | undefined | null): string {
  return (runs || []).map((r) => r.text).join('');
}

/* Types a text block can be converted to without losing its words. */
export const CONVERTIBLE: BlockType[] = ['paragraph', 'heading', 'callout', 'quote'];

export function convertBlock(block: Block, to: BlockType): Block {
  const runs: RichText = Array.isArray(block.content) && block.content.length && 'text' in (block.content[0] || {})
    ? block.content : [{ text: plainText(block.content) }];
  const fresh = newBlock(to);
  fresh.id = block.id;
  if (to === 'paragraph' || to === 'heading' || to === 'callout' || to === 'quote') {
    fresh.content = runs;
  }
  return fresh;
}

/* ---------------- API ---------------- */
export interface Violation {
  level: 'block' | 'warn';
  rule: string;
  message: string;
  block_id?: string | null;
}
export interface BlocksReport {
  word_count: number;
  reading_minutes: number;
  visuals: number;
  block_types: string[];
  effects: Record<string, number>;
  headings: [number, string][];
  violations: Violation[];
  blocking: number;
  warnings: number;
}
export interface BlocksResponse {
  article_id: string;
  content_format: 'legacy' | 'blocks';
  blocks: Block[];
  title: string | null;
  slug: string | null;
  meta_title: string | null;
  meta_description: string | null;
  primary_keyword: string;
  status: string;
  revision_number: number;
  can_edit: boolean;
  can_publish: boolean;
  report: BlocksReport | null;
  deferred_css_href: string;
  author_name: string;
}
export interface BlocksSave {
  blocks: Block[];
  title?: string;
  slug?: string;
  meta_title?: string;
  meta_description?: string;
  primary_keyword?: string;
  note?: string;
}
export interface BlocksSaveResponse {
  saved: boolean;
  revision_number: number;
  changed: boolean;
  report: BlocksReport;
  markdown_words: number;
}
export interface Revision {
  revision_number: number;
  created_at: string | null;
  created_by: string | null;
  note: string | null;
  block_count: number;
  title: string | null;
}
export interface PublishResult {
  published: boolean;
  url: string;
  page_path: string;
  css_path: string;
  indexnow: string | null;
  overridden: string[];
  message: string;
}
export interface MediaUpload {
  src: string;
  width: number;
  height: number;
  bytes: number;
  format: string;
}

export const blocksApi = {
  status: () => api.get<{ enabled: boolean; author_name: string; engine_version: string }>('/api/seo/blog-engine/status'),
  get: (id: string) => api.get<BlocksResponse>(`/api/seo/articles/${id}/blocks`),
  save: (id: string, body: BlocksSave) => api.put<BlocksSaveResponse>(`/api/seo/articles/${id}/blocks`, body),
  preview: (id: string, body: BlocksSave) =>
    api.post<{ html: string; report: BlocksReport }>(`/api/seo/articles/${id}/blocks/preview`, body),
  revisions: (id: string) => api.get<Revision[]>(`/api/seo/articles/${id}/blocks/revisions`),
  restore: (id: string, n: number) =>
    api.post<BlocksSaveResponse>(`/api/seo/articles/${id}/blocks/revisions/${n}/restore`),
  publish: (id: string, override_reason?: string) =>
    api.post<PublishResult>(`/api/seo/articles/${id}/blocks/publish`, override_reason ? { override_reason } : {}),
  upload: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api.post<MediaUpload>('/api/seo/media/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
};

/* The preview page references the site's stylesheets, fonts and media by
   site-relative URL. A <base> pointed at the live site resolves them, so the
   iframe shows the real chrome and fonts rather than a broken copy. */
export const SITE_ORIGIN = 'https://agenticaiautomation.co/';
export function previewSrcdoc(html: string): string {
  // The iframe is sandboxed without allow-scripts, so scripts would only log
  // console errors; drop them. Nothing on the page needs JS to be readable.
  const noScripts = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '');
  return noScripts.replace('<head>', `<head><base href="${SITE_ORIGIN}">`);
}
