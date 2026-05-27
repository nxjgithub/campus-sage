import { Button, Image, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { apiClient } from "../api/client";
import { CitationAssetItem, CitationItem } from "../api/modules/ask";
import { citationAssets } from "../utils/citationAssets";
import { normalizeAssetPath } from "./CitationAssetButton";

interface MarkdownMessageProps {
  content: string;
  citations?: CitationItem[];
  onCitationClick?: (citationId: number) => void;
}

const CITATION_LINK_PREFIX = "csage-citation-";
const CITATION_MARKER_PATTERN = /\[(\d+)\]/g;

export function MarkdownMessage({ content, citations = [], onCitationClick }: MarkdownMessageProps) {
  const markdownContent = useMemo(() => withCitationLinks(content), [content]);
  const assets = useMemo(() => uniqueCitationAssets(citations), [citations]);

  return (
    <div className="markdown-message">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            const citationId = parseCitationHref(href);
            if (citationId !== null) {
              return (
                <Button
                  size="small"
                  type="link"
                  className="citation-marker"
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    onCitationClick?.(citationId);
                  }}
                >
                  {children}
                </Button>
              );
            }
            return (
              <Typography.Link
                href={href}
                target="_blank"
                rel="noreferrer"
                onClick={(event) => {
                  event.stopPropagation();
                }}
              >
                {children}
              </Typography.Link>
            );
          },
          table: ({ children }) => (
            <div className="markdown-message__table-wrap">
              <table>{children}</table>
            </div>
          )
        }}
      >
        {markdownContent}
      </ReactMarkdown>
      <InlineAssets assets={assets} />
    </div>
  );
}

function withCitationLinks(content: string) {
  return content.replace(
    CITATION_MARKER_PATTERN,
    (_marker, citationId: string) => `[\\[${citationId}\\]](#${CITATION_LINK_PREFIX}${citationId})`
  );
}

function parseCitationHref(href?: string) {
  const prefix = `#${CITATION_LINK_PREFIX}`;
  if (!href?.startsWith(prefix)) {
    return null;
  }
  const citationId = Number(href.slice(prefix.length));
  return Number.isInteger(citationId) && citationId > 0 ? citationId : null;
}

function uniqueCitationAssets(citations: CitationItem[]) {
  const assets = new Map<string, CitationAssetItem>();
  for (const citation of citations) {
    for (const asset of citationAssets(citation)) {
      if (!assets.has(asset.asset_id)) {
        assets.set(asset.asset_id, asset);
      }
    }
  }
  return [...assets.values()];
}

function InlineAssets({ assets }: { assets: CitationAssetItem[] }) {
  if (!assets.length) {
    return null;
  }
  return (
    <section
      className="markdown-message__assets"
      onClick={(event) => {
        event.stopPropagation();
      }}
      onMouseDown={(event) => {
        event.stopPropagation();
      }}
    >
      <Typography.Text className="markdown-message__assets-title">图片证据</Typography.Text>
      <div className="markdown-message__asset-grid">
        {assets.map((asset) => (
          <InlineAssetImage asset={asset} key={asset.asset_id} />
        ))}
      </div>
    </section>
  );
}

function InlineAssetImage({ asset }: { asset: CitationAssetItem }) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let revoked = false;
    let objectUrl: string | null = null;
    apiClient
      .get<Blob>(normalizeAssetPath(asset.asset_url), { responseType: "blob" })
      .then((response) => {
        if (revoked) return;
        objectUrl = URL.createObjectURL(response.data);
        setUrl(objectUrl);
      })
      .catch(() => {
        setUrl(null);
      });
    return () => {
      revoked = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [asset.asset_url]);

  if (!url) {
    return null;
  }
  return (
    <figure
      className="markdown-message__asset"
      onClick={(event) => {
        event.stopPropagation();
      }}
      onMouseDown={(event) => {
        event.stopPropagation();
      }}
    >
      <Image src={url} alt={asset.asset_label || "图片证据"} preview={{ mask: "预览" }} />
      <figcaption>{asset.asset_label || asset.file_name || "图片证据"}</figcaption>
    </figure>
  );
}
