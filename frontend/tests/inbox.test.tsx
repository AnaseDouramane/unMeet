import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InboxView } from "@/components/inbox/inbox-view";
import { ReplyDraftPanel } from "@/components/inbox/reply-draft-panel";
import { api, ApiClientError } from "@/lib/api";
import type { InboxItem } from "@/lib/types";

function item(id: number, overrides: Partial<InboxItem> = {}): InboxItem {
  return {
    signal_id: id,
    source: "reddit",
    title: `Post ${id}`,
    url: `https://example.test/${id}`,
    author: "dana",
    published_at: "2026-11-02T09:30:00Z",
    intent: "pain_point",
    pain_quote: `quote ${id}`,
    products_mentioned: [],
    severity: 2,
    topic_id: 1,
    topic_name: "CRM",
    relevance_reason: `reason ${id}`,
    state: "new",
    note: null,
    updated_at: null,
    ...overrides,
  };
}

const counts = { new: 3, relevant: 0, not_relevant: 0, replied: 0 };

function mockApi(items: InboxItem[] = [item(1), item(2), item(3)]) {
  vi.spyOn(api, "getInbox").mockResolvedValue({ items, limit: 50, offset: 0 });
  vi.spyOn(api, "getInboxCounts").mockResolvedValue({ ...counts, new: items.length });
  vi.spyOn(api, "getTopics").mockResolvedValue({ items: [{ id: 1, name: "CRM" }] } as never);
  return vi.spyOn(api, "setInboxState").mockResolvedValue({ updated: 1 });
}

describe("inbox", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://api.test");
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    window.sessionStorage.clear();
  });

  it("shows the quote and why each signal matches, with counts on the tabs", async () => {
    mockApi();
    render(<InboxView />);

    expect(await screen.findByText("“quote 1”")).toBeInTheDocument();
    expect(screen.getByText("reason 2")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "New (3)" })).toHaveAttribute("aria-selected", "true");
  });

  it("asks for credentials when the API answers 401", async () => {
    vi.spyOn(api, "getInbox").mockRejectedValue(new ApiClientError("authentication is required", 401));
    vi.spyOn(api, "getInboxCounts").mockResolvedValue(counts);
    vi.spyOn(api, "getTopics").mockResolvedValue({ items: [] } as never);
    render(<InboxView />);

    expect(await screen.findByRole("form", { name: "Connect" })).toBeInTheDocument();
  });

  it("moves with j/k and marks the current item with r, x and e", async () => {
    const setState = mockApi();
    render(<InboxView />);
    await screen.findByText("“quote 1”");

    fireEvent.keyDown(window, { key: "j" }); // cursor on the second item
    fireEvent.keyDown(window, { key: "r" });
    await waitFor(() => expect(setState).toHaveBeenCalledWith([2], "relevant"));
    await waitFor(() => expect(screen.queryByText("“quote 2”")).not.toBeInTheDocument());
    expect(screen.getByRole("tab", { name: "New (2)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Relevant (1)" })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "x" });
    await waitFor(() => expect(setState).toHaveBeenLastCalledWith([3], "not_relevant"));
  });

  it("ignores shortcuts while typing and with modifier keys", async () => {
    const setState = mockApi();
    render(<InboxView />);
    await screen.findByText("“quote 1”");

    const topic = screen.getByLabelText("Topic");
    fireEvent.keyDown(topic, { key: "r" });
    fireEvent.keyDown(window, { key: "r", ctrlKey: true });
    fireEvent.keyDown(window, { key: "r", metaKey: true });
    expect(setState).not.toHaveBeenCalled();
  });

  it("applies a shortcut to every selected item at once", async () => {
    const setState = mockApi();
    render(<InboxView />);
    await screen.findByText("“quote 1”");

    fireEvent.click(screen.getByLabelText("Select Post 1"));
    fireEvent.click(screen.getByLabelText("Select Post 3"));
    expect(screen.getByLabelText("Bulk actions")).toHaveTextContent("2 selected");
    fireEvent.click(within(screen.getByLabelText("Bulk actions")).getByText("Mark not relevant"));

    await waitFor(() => expect(setState).toHaveBeenCalledWith([1, 3], "not_relevant"));
    await waitFor(() => expect(screen.queryByLabelText("Bulk actions")).not.toBeInTheDocument());
  });

  it("keeps the item and shows the error when saving fails", async () => {
    const setState = mockApi();
    setState.mockRejectedValue(new ApiClientError("forbidden", 403));
    render(<InboxView />);
    await screen.findByText("“quote 1”");

    fireEvent.keyDown(window, { key: "r" });
    expect(await screen.findByRole("alert")).toHaveTextContent("forbidden");
    expect(screen.getByText("“quote 1”")).toBeInTheDocument();
  });

  it("explains an empty inbox and filters by topic", async () => {
    const getInbox = vi.spyOn(api, "getInbox").mockResolvedValue({ items: [], limit: 50, offset: 0 });
    vi.spyOn(api, "getInboxCounts").mockResolvedValue({ ...counts, new: 0 });
    vi.spyOn(api, "getTopics").mockResolvedValue({ items: [{ id: 1, name: "CRM" }] } as never);
    render(<InboxView />);

    expect(await screen.findByText("Nothing new")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "1" } });
    await waitFor(() => expect(getInbox).toHaveBeenLastCalledWith({ state: "new", topic_id: 1, limit: 50 }));
  });

  it("switches tabs and requests that state", async () => {
    const getInbox = vi.spyOn(api, "getInbox").mockResolvedValue({ items: [item(9, { state: "replied" })], limit: 50, offset: 0 });
    vi.spyOn(api, "getInboxCounts").mockResolvedValue(counts);
    vi.spyOn(api, "getTopics").mockResolvedValue({ items: [] } as never);
    render(<InboxView />);
    await screen.findByText("“quote 9”");

    fireEvent.click(screen.getByRole("tab", { name: /^Replied/ }));
    await waitFor(() => expect(getInbox).toHaveBeenLastCalledWith({ state: "replied", topic_id: undefined, limit: 50 }));
  });
});

describe("reply draft", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const draft = {
    draft: "Disclosure: I work at Acme. Try merging on email.",
    mentions_product: true,
    disclosure_added: true,
    community_rules: "Check the subreddit rules.",
    note: "Review and edit it, then post it yourself. unMeet never posts for you.",
  };

  it("shows an editable draft with the community rules and copies the edited text", async () => {
    vi.spyOn(api, "getReplyDraft").mockResolvedValue(draft);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<ReplyDraftPanel signalId={5} onClose={() => undefined} />);

    const box = await screen.findByLabelText("Draft text");
    expect(box).toHaveValue(draft.draft);
    expect(screen.getByText(/Check the subreddit rules/)).toBeInTheDocument();
    expect(screen.getByText(/never posts for you/)).toBeInTheDocument();
    expect(screen.getByText(/disclosure line was added/)).toBeInTheDocument();

    fireEvent.change(box, { target: { value: "Edited text" } });
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("Edited text"));
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("shows why a draft could not be written", async () => {
    vi.spyOn(api, "getReplyDraft").mockRejectedValue(new ApiClientError("the monthly AI budget is used up", 402));
    render(<ReplyDraftPanel signalId={5} onClose={() => undefined} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("AI budget");
  });
});
