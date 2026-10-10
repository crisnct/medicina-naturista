import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { api, ApiError } from "./api/client";

Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });

const activeMessage = "Chatul este deja deschis într-un alt tab sau browser. Este permisă o singură sesiune per adresă IP.";

afterEach(() => vi.restoreAllMocks());

describe("session admission", () => {
  it("blocks searching after a rejected session and allows retry after the other page closes", async () => {
    const session = vi.spyOn(api, "getSession")
      .mockRejectedValueOnce(new ApiError(429, activeMessage, "SESSION_ALREADY_ACTIVE"))
      .mockResolvedValue({ history: [] });
    vi.spyOn(api, "getCategories").mockResolvedValue({ tree: null, defaultSelection: [] });
    const send = vi.spyOn(api, "sendMessage").mockResolvedValue({ messages: [], startSearch: false });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><App /></QueryClientProvider>);

    expect(await screen.findByRole("alert")).toHaveTextContent(activeMessage);
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
