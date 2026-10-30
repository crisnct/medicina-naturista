import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { applyDocumentLanguage } from "./lib/texts";
import { App } from "./App";
import "@fontsource/merienda/800.css";
import "@fontsource/roboto-condensed/400.css";
import "@fontsource/roboto-condensed/500.css";
import "@fontsource/roboto-condensed/700.css";
import "@fontsource/roboto-condensed/400-italic.css";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

applyDocumentLanguage();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
