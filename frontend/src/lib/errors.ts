/** Map a backend error code/reason to a friendly, user-facing message. */
const PATTERNS: Array<[RegExp, string]> = [
  [
    /not_a_contract/i,
    "This doesn't look like a contract. Please paste a rental, employment, NDA, or vendor agreement and try again.",
  ],
  [
    /injection/i,
    "This text looks like it contains instructions to the AI rather than a contract. Please paste a normal contract.",
  ],
  [
    /api_key|generation_failed|retries_exhausted|resource_exhausted|unavailable|503|no_provider/i,
    "The analysis service is temporarily unavailable. Please try again in a moment.",
  ],
  [
    /too short|min|length|100 characters/i,
    "That text is too short to analyse. Please paste the full contract (at least a few paragraphs).",
  ],
];

/** Turn a raw error (code, reason, or message) into human-readable copy. */
export function describeError(raw: string | null | undefined): string {
  const text = (raw ?? "").trim();
  for (const [pattern, message] of PATTERNS) {
    if (pattern.test(text)) {
      return message;
    }
  }
  // Already a human sentence (has spaces, not a bare snake_case/colon code)? show it.
  if (text && /\s/.test(text) && !/^[a-z0-9_:]+$/i.test(text)) {
    return text;
  }
  return "We couldn't analyse this document. Please check the text and try again.";
}
