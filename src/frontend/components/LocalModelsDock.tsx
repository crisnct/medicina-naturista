import { useState } from "react";
import type { LocalModel, LocalModelRuntime } from "../api/types";
import { useLocalModels, useUnloadLocalModel } from "../hooks/useLocalModels";
import { tr } from "../lib/texts";

const RUNTIMES: LocalModelRuntime[] = ["ollama", "vllm", "colibri"];
const RUNTIME_LABELS = {
  ollama: "interface.local_models_runtime_ollama",
  vllm: "interface.local_models_runtime_vllm",
  colibri: "interface.local_models_runtime_colibri",
} as const;
const ROLE_LABELS = {
  query_embedding: "interface.local_models_role_query_embedding",
  classifier: "interface.local_models_role_classifier",
  report: "interface.local_models_role_report",
  index_embedding: "interface.local_models_role_index_embedding",
  translation: "interface.local_models_role_translation",
  unknown: "interface.local_models_role_unknown",
} as const;
const OPEN_KEY = "naturist_local_models_open";
// Below this width the window would cover the chat, so it starts as the pill there.
const NARROW_QUERY = "(max-width: 640px)";

function initiallyOpen(): boolean {
  try {
    if (window.matchMedia?.(NARROW_QUERY).matches) return false;
    return localStorage.getItem(OPEN_KEY) !== "0";
  } catch {
    return true;
  }
}

function Placement({ model }: { model: LocalModel }) {
  const prefix = model.approximate ? "~" : "";
  const title = model.approximate ? tr("interface.local_models_approximate") : undefined;
  if (model.ramPct === null || model.vramPct === null) {
    return <span className="local-model-place" title={title}>{tr("interface.local_models_split_unknown")}</span>;
  }
  if (model.vramPct === 100 || model.ramPct === 100) {
    return (
      <span className="local-model-place" title={title}>
        {prefix}{model.vramPct === 100 ? tr("interface.local_models_vram") : tr("interface.local_models_ram")}
      </span>
    );
  }
  return (
    <span className="local-model-split" title={title}>
      <span className="local-model-place">
        {prefix}{tr("interface.local_models_split", { ram: model.ramPct, vram: model.vramPct })}
      </span>
      <span className="local-model-bar" aria-hidden="true">
        <span className="local-model-bar-ram" style={{ width: `${model.ramPct}%` }} />
        <span className="local-model-bar-vram" style={{ width: `${model.vramPct}%` }} />
      </span>
    </span>
  );
}

// The local AI models in memory right now, fixed at the lower right; collapsible into a pill.
export function LocalModelsDock() {
  const [open, setOpen] = useState(initiallyOpen);
  const query = useLocalModels();
  const unload = useUnloadLocalModel();
  const state = query.data;
  const models = state?.available ? state.models : [];

  const toggle = (next: boolean) => {
    setOpen(next);
    try {
      localStorage.setItem(OPEN_KEY, next ? "1" : "0");
    } catch {
      // A browser that refuses storage still collapses the window for this page.
    }
  };

  if (!open) {
    return (
      <button type="button" className="local-models-pill" aria-expanded="false"
        aria-label={tr("interface.local_models_toggle_open")} title={tr("interface.local_models_title")}
        onClick={() => toggle(true)}>
        <span aria-hidden="true">🧠</span>
        {state?.available && <span className="local-models-count">{models.length}</span>}
      </button>
    );
  }

  const unavailable = query.isError || (state !== undefined && !state.available);
  return (
    <aside className="local-models-dock" aria-label={tr("interface.local_models_title")}>
      <header className="local-models-header">
        <h2>{tr("interface.local_models_title")}</h2>
        <button type="button" className="local-models-collapse" aria-expanded="true"
          aria-label={tr("interface.local_models_toggle_close")} title={tr("interface.local_models_toggle_close")}
          onClick={() => toggle(false)}>
          <span aria-hidden="true">−</span>
        </button>
      </header>
      {unavailable ? (
        <p className="local-models-note">{tr("interface.local_models_unavailable")}</p>
      ) : state === undefined ? (
        <span className="loader" aria-hidden="true" />
      ) : models.length === 0 ? (
        <p className="local-models-note">{tr("interface.local_models_empty")}</p>
      ) : (
        RUNTIMES.filter((runtime) => models.some((model) => model.runtime === runtime)).map((runtime) => (
          <section key={runtime} className="local-models-group">
            <h3>{tr(RUNTIME_LABELS[runtime])}</h3>
            <ul>
              {models.filter((model) => model.runtime === runtime).map((model) => (
                <li key={`${runtime}:${model.name}`} className="local-model">
                  <div className="local-model-line">
                    <span className="local-model-name">{model.name}</span>
                    {model.loading && <span className="local-model-loading">{tr("interface.local_models_loading")}</span>}
                    <Placement model={model} />
                    {state?.canUnload && (
                      <button type="button" className="local-model-unload"
                        aria-label={tr("interface.local_models_unload", { name: model.name })}
                        title={tr("interface.local_models_unload", { name: model.name })}
                        disabled={unload.isPending}
                        onClick={() => unload.mutate(model)}>
                        <span aria-hidden="true">{unload.isPending && unload.variables?.id === model.id ? "…" : "×"}</span>
                      </button>
                    )}
                  </div>
                  {model.roles.map((role) => (
                    <p key={role} className="local-model-role">{tr(ROLE_LABELS[role])}</p>
                  ))}
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
      {state?.available && state.partial && <p className="local-models-note">{tr("interface.local_models_partial")}</p>}
      {unload.isError && <p className="local-models-note" role="alert">{tr("interface.local_models_unload_failed")}</p>}
    </aside>
  );
}
