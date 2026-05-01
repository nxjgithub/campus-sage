import { Button, Image, Space, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { apiClient } from "../api/client";
import { CitationAssetItem, CitationItem } from "../api/modules/ask";
import { splitCitationMarkers } from "../utils/citation";
import { citationAssets } from "../utils/citationAssets";
import { normalizeAssetPath } from "./CitationAssetButton";

interface MarkdownMessageProps {
  content: string;
  citations?: CitationItem[];
  onCitationClick?: (citationId: number) => void;
}

export function MarkdownMessage({ content, citations = [], onCitationClick }: MarkdownMessageProps) {
  const tokens = splitCitationMarkers(content);
  const citationMap = useMemo(() => {
    return new Map(citations.map((citation) => [citation.citation_id, citation]));
  }, [citations]);
  const hasInlineAssets = tokens.some((token) => {
    if (token.type !== "marker") return false;
    const citation = citationMap.get(token.citationId);
    return citation ? citationAssets(citation).length > 0 : false;
  });
  const fallbackAssets = hasInlineAssets
    ? []
    : citations.flatMap((citation) => citationAssets(citation));

  return (
    <div className="markdown-message">
      {tokens.map((token, index) => {
        if (token.type === "marker") {
          const citation = citationMap.get(token.citationId);
          const assets = citation ? citationAssets(citation) : [];
          return (
            <span className="markdown-message__citation" key={`${token.marker}_${index}`}>
              <Button
                size="small"
                type="link"
                className="citation-marker"
                onClick={(event) => {
                  event.stopPropagation();
                  onCitationClick?.(token.citationId);
                }}
              >
                {token.marker}
              </Button>
              <InlineAssets assets={assets} />
            </span>
          );
        }
        return <MarkdownText key={`text_${index}`} value={token.value} />;
      })}
      <InlineAssets assets={fallbackAssets} />
    </div>
  );
}

function MarkdownText({ value }: { value: string }) {
  if (!value) {
    return null;
  }
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children }) => (
          <Typography.Link href={href} target="_blank" rel="noreferrer">
            {children}
          </Typography.Link>
        ),
        table: ({ children }) => (
          <div className="markdown-message__table-wrap">
            <table>{children}</table>
          </div>
        )
      }}
    >
      {value}
    </ReactMarkdown>
  );
}

function InlineAssets({ assets }: { assets: CitationAssetItem[] }) {
  if (!assets.length) {
    return null;
  }
  return (
    <Space className="markdown-message__assets" size={10} wrap>
      {assets.map((asset) => (
        <InlineAssetImage asset={asset} key={asset.asset_id} />
      ))}
    </Space>
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
    <figure className="markdown-message__asset">
      <Image src={url} alt={asset.asset_label || "图片证据"} />
      <figcaption>{asset.asset_label || asset.file_name || "图片证据"}</figcaption>
    </figure>
  );
}
