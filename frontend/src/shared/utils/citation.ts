export type CitationToken =
  | { type: "text"; value: string }
  | { type: "marker"; citationId: number; marker: string };

const CITATION_MARKER_PATTERN = /\[(\d+)\]/g;

export function splitCitationMarkers(content: string): CitationToken[] {
  const tokens: CitationToken[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = CITATION_MARKER_PATTERN.exec(content)) !== null) {
    const start = match.index;
    const end = CITATION_MARKER_PATTERN.lastIndex;
    if (start > lastIndex) {
      tokens.push({
        type: "text",
        value: content.slice(lastIndex, start)
      });
    }
    tokens.push({
      type: "marker",
      citationId: Number(match[1]),
      marker: match[0]
    });
    lastIndex = end;
  }

  if (lastIndex < content.length) {
    tokens.push({
      type: "text",
      value: content.slice(lastIndex)
    });
  }

  if (!tokens.length) {
    return [{ type: "text", value: content }];
  }

  return tokens;
}
