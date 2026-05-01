import { CitationAssetItem, CitationItem } from "../api/modules/ask";

export function citationAssets(citation: CitationItem): CitationAssetItem[] {
  if (Array.isArray(citation.assets) && citation.assets.length > 0) {
    return citation.assets.filter((asset) => Boolean(asset.asset_id && asset.asset_url));
  }
  if (citation.asset_id && citation.asset_url) {
    return [
      {
        asset_id: citation.asset_id,
        asset_label: citation.asset_label,
        asset_url: citation.asset_url
      }
    ];
  }
  return [];
}
