// Only a closed metadata block at the beginning of a Markdown source is folded.
// The caller retains the untouched content for exact source comparison.
export function readableSource(content = '', path = '') {
  const original = typeof content === 'string' ? content : '';
  if (!/\.md$/i.test(path)) return { body: original, folded: false };
  const block = original.match(/^\uFEFF?---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/);
  if (!block || !/^(?:title|type|created_at|occurred_at|reviewed_at|material_role|tags):/m.test(block[1])) {
    return { body: original, folded: false };
  }
  const body = original.slice(block[0].length);
  // Metadata-only files still need their content visible on first open.
  return body.trim() ? { body, folded: true } : { body: original, folded: false };
}
