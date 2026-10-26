import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { api, ApiError } from "./api/client";

Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });

const capacityMessage = "Serviciul este temporar indisponibil. Încercați mai târziu.";

afterEach(() => vi.restoreAllMocks());
beforeEach(() => {
  vi.spyOn(api, "getStartup").mockResolvedValue({ status: "ready", message: null });
  vi.spyOn(api, "getReportModels").mockResolvedValue({ models: ["ollama-gemma4:12b"] });
});

describe("session admission", () => {
  it("explains the session creation limit and shows the server's remaining wait", async () => {
    const session = vi.spyOn(api, "getSession")
      .mockRejectedValueOnce(new ApiError(429, "Prea multe cereri.", "RATE_LIMIT", 48))
      .mockResolvedValue({ history: [] });
    vi.spyOn(api, "getCategories").mockResolvedValue({ tree: null, defaultSelection: [] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><App /></QueryClientProvider>);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Ați deschis prea multe conversații într-un minut.");
    expect(alert).toHaveTextContent("Așteptați 48 de secunde");
    expect(session).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Verifică din nou" }));
    await waitFor(() => expect(screen.getByRole("textbox")).toBeEnabled());
    const topExamples = screen.getAllByRole("button").filter((button) => button.textContent?.includes("Top "));
    expect(topExamples).toHaveLength(2);
    expect(topExamples[0]).toHaveTextContent("Top 100 produse naturiste");
    fireEvent.click(topExamples[1]);
    expect(screen.getByRole("textbox")).toHaveValue("Top 10 produse naturiste pentru gripa");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("blocks searching after a failed session and allows retry when capacity is available", async () => {
    const session = vi.spyOn(api, "getSession")
      .mockRejectedValueOnce(new ApiError(503, "Capacitatea aplicației este ocupată.", "GLOBAL_SESSION_LIMIT"))
      .mockResolvedValue({ history: [] });
    vi.spyOn(api, "getCategories").mockResolvedValue({ tree: null, defaultSelection: [] });
    const send = vi.spyOn(api, "sendMessage").mockResolvedValue({ messages: [], startSearch: false });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><App /></QueryClientProvider>);

    expect(await screen.findByRole("alert")).toHaveTextContent(capacityMessage);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "📨 Trimite" })).not.toBeInTheDocument();
    expect(send).not.toHaveBeenCalled();
    expect(session).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Verifică din nou" }));
    const input = await screen.findByRole("textbox");
    await waitFor(() => expect(input).toBeEnabled());
    fireEvent.change(input, { target: { value: "gripă" } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("does not allow Enter to send while the session is still being initialized", () => {
    vi.spyOn(api, "getSession").mockImplementation(() => new Promise(() => {}));
    vi.spyOn(api, "getCategories").mockResolvedValue({ tree: null, defaultSelection: [] });
    const send = vi.spyOn(api, "sendMessage");
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
    const input = screen.getByRole("textbox");
    expect(input).toBeDisabled();
    fireEvent.change(input, { target: { value: "gripă" } });
    fireEvent.submit(input.closest("form")!);
    expect(send).not.toHaveBeenCalled();
  });
});
