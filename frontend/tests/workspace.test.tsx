import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConnectPanel } from "@/components/auth/connect-panel";
import { OnboardingWizard } from "@/components/onboarding/onboarding-wizard";
import { SettingsView } from "@/components/settings/settings-view";
import { api, ApiClientError } from "@/lib/api";
import { clearCredential, getCredential, getWorkspaceId, saveCredential } from "@/lib/auth";
import type { Proposal, WorkspaceInfo } from "@/lib/types";

const plan = { name: "team", monthly_price_eur: 149, max_topics: 25, max_seats: 10, llm_budget_usd: 29, webhooks: true, daily_digest: true };
const workspace: WorkspaceInfo = { id: 1, name: "Acme", slug: "acme", plan, role: "owner", topics_used: 2, seats_used: 1 };

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://api.test");
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe("credentials", () => {
  it("stores, trims and clears the key and workspace for the tab", () => {
    expect(getCredential()).toBe("");
    saveCredential("  um_abc_secret ", " 7 ");
    expect([getCredential(), getWorkspaceId()]).toEqual(["um_abc_secret", "7"]);
    clearCredential();
    expect([getCredential(), getWorkspaceId()]).toEqual(["", ""]);
  });

  it("sends the stored key and workspace with every API request", async () => {
    saveCredential("um_abc_secret", "7");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [] }) });
    vi.stubGlobal("fetch", fetchMock);

    await api.getTopics();

    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer um_abc_secret");
    expect(headers["X-Workspace-ID"]).toBe("7");
  });

  it("sends no credentials when none are stored, and an explicit key wins", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [] }) });
    vi.stubGlobal("fetch", fetchMock);
    await api.getTopics();
    expect(fetchMock.mock.calls[0][1].headers).not.toHaveProperty("Authorization");

    saveCredential("stored", "");
    await api.createTopic({ name: "x" } as never, "explicit");
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe("Bearer explicit");
  });
});

describe("connect panel", () => {
  it("verifies the key before keeping it", async () => {
    vi.spyOn(api, "getWorkspace").mockResolvedValue(workspace);
    const onConnected = vi.fn();
    render(<ConnectPanel onConnected={onConnected} />);

    fireEvent.change(screen.getByLabelText("API key"), { target: { value: "um_abc_secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    expect(await screen.findByText(/Connected to/)).toHaveTextContent("Acme");
    expect(getCredential()).toBe("um_abc_secret");
    expect(onConnected).toHaveBeenCalledWith(workspace);
  });

  it("forgets a rejected key and says so", async () => {
    vi.spyOn(api, "getWorkspace").mockRejectedValue(new ApiClientError("invalid", 401));
    render(<ConnectPanel />);

    fireEvent.change(screen.getByLabelText("API key"), { target: { value: "bad" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("not accepted");
    expect(getCredential()).toBe("");
  });

  it("disconnects", async () => {
    saveCredential("um_abc_secret");
    vi.spyOn(api, "getWorkspace").mockResolvedValue(workspace);
    render(<ConnectPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));
    expect(getCredential()).toBe("");
    expect(screen.getByRole("form", { name: "Connect" })).toBeInTheDocument();
  });
});

const proposal: Proposal = {
  source_url: "https://acme.test/",
  product_summary: "Acme cleans CRM duplicates.",
  icp: "RevOps managers",
  competitors: ["Dedupely"],
  topics: [
    { name: "CRM duplicates", description: "People with duplicate contacts", intents: ["pain_point"], products: ["HubSpot"] },
    { name: "Dedupe tools", description: "Asking for a tool", intents: [], products: [] },
  ],
};

describe("onboarding", () => {
  it("analyses a URL, lets the user edit and remove topics, then confirms", async () => {
    const analyze = vi.spyOn(api, "analyzeSite").mockResolvedValue(proposal);
    const confirm = vi.spyOn(api, "confirmOnboarding").mockResolvedValue({ created: [{ id: 1 }] as never, skipped: [{ name: "Dedupe tools", reason: "free plan" }] });
    render(<OnboardingWizard />);

    fireEvent.change(screen.getByLabelText("Your website"), { target: { value: " https://acme.test " } });
    fireEvent.click(screen.getByRole("button", { name: "Analyse" }));
    expect(await screen.findByText("Dedupely", { exact: false })).toBeInTheDocument();
    expect(analyze).toHaveBeenCalledWith("https://acme.test");

    fireEvent.change(screen.getByLabelText("Topic 1 description"), { target: { value: "Edited description" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Remove" })[1]);
    fireEvent.click(screen.getByRole("button", { name: "Create 1 topic" }));

    await waitFor(() =>
      expect(confirm).toHaveBeenCalledWith({
        website_url: "https://acme.test/",
        product_summary: "Acme cleans CRM duplicates.",
        topics: [{ ...proposal.topics[0], description: "Edited description" }],
      }),
    );
    expect(await screen.findByText("1 topic created")).toBeInTheDocument();
    expect(screen.getByText(/was skipped: free plan/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the inbox" })).toHaveAttribute("href", "/inbox");
  });

  it("blocks confirmation while a topic is empty and shows analysis errors", async () => {
    vi.spyOn(api, "analyzeSite").mockResolvedValueOnce(proposal);
    render(<OnboardingWizard />);
    fireEvent.change(screen.getByLabelText("Your website"), { target: { value: "https://acme.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Analyse" }));
    await screen.findByLabelText("Topic 1 name");
    fireEvent.change(screen.getByLabelText("Topic 1 name"), { target: { value: "  " } });
    expect(screen.getByRole("button", { name: "Create 2 topics" })).toBeDisabled();
  });

  it("reports why the site could not be analysed and asks to connect on 401", async () => {
    const analyze = vi.spyOn(api, "analyzeSite").mockRejectedValueOnce(new ApiClientError("the host must be public", 400));
    render(<OnboardingWizard />);
    fireEvent.change(screen.getByLabelText("Your website"), { target: { value: "https://10.0.0.1" } });
    fireEvent.click(screen.getByRole("button", { name: "Analyse" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("must be public");

    analyze.mockRejectedValueOnce(new ApiClientError("auth", 401));
    fireEvent.click(screen.getByRole("button", { name: "Analyse" }));
    expect(await screen.findByRole("form", { name: "Connect" })).toBeInTheDocument();
  });
});

describe("settings", () => {
  function mockSettings(info: WorkspaceInfo = workspace) {
    vi.spyOn(api, "getWorkspace").mockResolvedValue(info);
    vi.spyOn(api, "getMembers").mockResolvedValue([{ user_id: 1, email: "owner@acme.test", role: "owner" }]);
    vi.spyOn(api, "getApiKeys").mockResolvedValue([
      { id: 1, name: "ci", prefix: "ab12cd34", created_at: null, last_used_at: null, revoked_at: null },
    ]);
    vi.spyOn(api, "getChannels").mockResolvedValue([]);
  }

  it("shows plan usage and shows a new API key exactly once", async () => {
    mockSettings();
    saveCredential("um_abc_secret");
    vi.spyOn(api, "createApiKey").mockResolvedValue({
      id: 2, name: "clay", prefix: "ee00ff11", created_at: null, last_used_at: null, revoked_at: null, key: "um_ee00ff11_TOPSECRET",
    });
    render(<SettingsView />);

    expect(await screen.findByText("Plan: team")).toBeInTheDocument();
    expect(screen.getByText(/Topics 2\/25/)).toBeInTheDocument();
    expect(screen.getByText("um_ab12cd34_…")).toBeInTheDocument();
    expect(screen.queryByText(/TOPSECRET/)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Key name"), { target: { value: "clay" } });
    fireEvent.click(screen.getByRole("button", { name: "Create key" }));
    expect(await screen.findByRole("status")).toHaveTextContent("um_ee00ff11_TOPSECRET");
  });

  it("hides management sections from plain members", async () => {
    mockSettings({ ...workspace, role: "member" });
    saveCredential("um_abc_secret");
    render(<SettingsView />);

    expect(await screen.findByText("Plan: team")).toBeInTheDocument();
    expect(screen.queryByLabelText("Key name")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Member email")).not.toBeInTheDocument();
    expect(screen.queryByText("Deliveries")).not.toBeInTheDocument();
  });

  it("adds a delivery channel and shows plan errors from the API", async () => {
    mockSettings();
    saveCredential("um_abc_secret");
    const add = vi.spyOn(api, "addChannel").mockRejectedValueOnce(new ApiClientError("Slack delivery is not included in the free plan", 402));
    render(<SettingsView />);
    await screen.findByText("Deliveries");

    fireEvent.change(screen.getByLabelText("Channel type"), { target: { value: "slack" } });
    fireEvent.change(screen.getByLabelText("Channel target"), { target: { value: "https://hooks.slack.com/services/a/b/c" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("not included in the free plan");
    expect(add).toHaveBeenCalledWith({ kind: "slack", target: "https://hooks.slack.com/services/a/b/c", frequency: "daily" });
  });

  it("asks to connect when there is no valid credential", async () => {
    vi.spyOn(api, "getWorkspace").mockRejectedValue(new ApiClientError("auth", 401));
    render(<SettingsView />);
    expect(await screen.findByRole("form", { name: "Connect" })).toBeInTheDocument();
  });
});
