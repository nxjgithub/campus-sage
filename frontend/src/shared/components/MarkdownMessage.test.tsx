import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CitationItem } from "../api/modules/ask";
import { MarkdownMessage } from "./MarkdownMessage";

function citation(citationId: number): CitationItem {
  return {
    citation_id: citationId,
    doc_id: `doc_${citationId}`,
    doc_name: "系统使用手册",
    page_start: citationId,
    page_end: citationId,
    section_path: "AI简历",
    chunk_id: `chunk_${citationId}`,
    snippet: "AI简历制作步骤",
    score: 0.9
  };
}

describe("MarkdownMessage", () => {
  it("keeps citation markers inside markdown list layout", async () => {
    const user = userEvent.setup();
    const onCitationClick = vi.fn();
    render(
      <MarkdownMessage
        content={"1. 新建空白简历[1]\n2. 复制已有简历[2]"}
        citations={[citation(1), citation(2)]}
        onCitationClick={onCitationClick}
      />
    );

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText("新建空白简历")).toBeInTheDocument();
    expect(within(items[1]).getByText("复制已有简历")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "[1]" }));
    expect(onCitationClick).toHaveBeenCalledWith(1);
  });
});
