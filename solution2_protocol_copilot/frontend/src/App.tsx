import { useEffect } from "react";
import EditorPage from "@/pages/EditorPage";
import { useModeStore, type LLMMode } from "@/stores/modeStore";

export default function App() {
  // On mount, sync the dropdown's initial value with whatever the backend
  // was started with (env-var LLM_MODE). Silent best-effort: if the call
  // fails, the store keeps its default ("mock"), which won't break anything.
  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((data) => {
        const m: unknown = data?.llm_mode;
        if (m === "mock" || m === "fake" || m === "cached" || m === "live") {
          useModeStore.getState().setMode(m as LLMMode);
        }
      })
      .catch(() => {
        /* keep default */
      });
  }, []);

  return <EditorPage />;
}
