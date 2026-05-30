import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Download, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { fetchAmendmentPackage, type AmendmentPackageResponse } from "@/lib/api";

interface Props {
  protocolId: string;
  open: boolean;
  onClose: () => void;
}

// Theatrical messages shown sequentially during the 1.5s generating stage.
// Each holds for 500ms; the third lingers until the package arrives.
const GENERATING_MESSAGES = [
  "Compiling accepted amendments…",
  "Computing redline diff…",
  "Assembling package metadata…",
];

const GENERATING_TOTAL_MS = 1500;
const MESSAGE_STEP_MS = 500;

export default function ExportModal({ protocolId, open, onClose }: Props) {
  const [stage, setStage] = useState<"generating" | "ready" | "error">("generating");
  const [data, setData] = useState<AmendmentPackageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msgIdx, setMsgIdx] = useState(0);

  // On open: fire the backend call AND the theatrical timer in parallel.
  // Both must settle before we flip to "ready".
  useEffect(() => {
    if (!open) return;
    setStage("generating");
    setData(null);
    setError(null);
    setMsgIdx(0);

    const startedAt = Date.now();
    let cancelled = false;

    const fetchPromise = fetchAmendmentPackage(protocolId);

    fetchPromise
      .then((resp) => {
        if (cancelled) return;
        const elapsed = Date.now() - startedAt;
        const remaining = Math.max(0, GENERATING_TOTAL_MS - elapsed);
        window.setTimeout(() => {
          if (cancelled) return;
          setData(resp);
          setStage("ready");
        }, remaining);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        setStage("error");
      });

    return () => { cancelled = true; };
  }, [open, protocolId]);

  // Cycle through the generating messages every MESSAGE_STEP_MS
  useEffect(() => {
    if (!open || stage !== "generating") return;
    const id = window.setInterval(() => {
      setMsgIdx((i) => Math.min(i + 1, GENERATING_MESSAGES.length - 1));
    }, MESSAGE_STEP_MS);
    return () => window.clearInterval(id);
  }, [open, stage]);

  // Escape to close
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);

  const handleDownload = () => {
    if (!data) return;
    const blob = new Blob([data.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Amendment_Package_${data.protocol_id}_${data.from_version}_to_${data.to_version}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (!open) return null;

  return (
    <AnimatePresence>
      <motion.div
        key="backdrop"
        className="fixed inset-0 z-50 flex items-center justify-center"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
      >
        {/* Backdrop */}
        <div
          className="absolute inset-0 bg-slate-900/50"
          onClick={onClose}
        />

        {/* Dialog */}
        <motion.div
          key="dialog"
          className="relative bg-white rounded-lg shadow-2xl w-[min(800px,90vw)] h-[min(720px,85vh)] flex flex-col overflow-hidden"
          initial={{ opacity: 0, y: 12, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, scale: 0.98 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
        >
          {stage === "generating" && <GeneratingView msgIdx={msgIdx} />}
          {stage === "error" && <ErrorView error={error} onClose={onClose} />}
          {stage === "ready" && data && (
            <ReadyView data={data} onDownload={handleDownload} onClose={onClose} />
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

// ── Stage views ────────────────────────────────────────────────────────────────

function GeneratingView({ msgIdx }: { msgIdx: number }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 px-8">
      <Loader2 size={36} className="text-teal-600 animate-spin" strokeWidth={2} />
      <div className="text-sm text-slate-600 font-medium">
        Generating amendment package…
      </div>
      <AnimatePresence mode="wait">
        <motion.div
          key={msgIdx}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.18 }}
          className="text-xs italic text-slate-400"
        >
          {GENERATING_MESSAGES[msgIdx]}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

function ErrorView({ error, onClose }: { error: string | null; onClose: () => void }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 px-8 text-center">
      <p className="text-sm font-semibold text-red-700">Couldn't generate amendment package</p>
      <p className="text-xs text-slate-500 max-w-md">{error ?? "Unknown error"}</p>
      <button
        onClick={onClose}
        className="mt-2 px-3 py-1.5 text-xs font-medium text-slate-600 border border-slate-300 rounded-md hover:bg-slate-50"
      >
        Close
      </button>
    </div>
  );
}

function ReadyView({
  data, onDownload, onClose,
}: {
  data: AmendmentPackageResponse;
  onDownload: () => void;
  onClose: () => void;
}) {
  return (
    <>
      {/* Header */}
      <div className="shrink-0 px-6 pt-5 pb-3 border-b border-slate-200 bg-gradient-to-b from-teal-50/40 to-white">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-green-100 text-green-700 text-xs font-bold">
            ✓
          </span>
          <h2 className="text-base font-bold text-navy-800">
            Amendment package ready
          </h2>
        </div>
        <p className="text-xs text-slate-500 mt-1 font-mono">
          {data.from_version} → {data.to_version} · {data.changes.length} change
          {data.changes.length === 1 ? "" : "s"} · Risk{" "}
          <span className="text-red-700 font-semibold">{data.overall_risk_before}%</span>
          {" → "}
          <span className="text-green-700 font-semibold">{data.overall_risk_after}%</span>
        </p>
      </div>

      {/* Preview body — react-markdown rendered with print-feel typography */}
      <div className="flex-1 overflow-y-auto px-8 py-6 bg-slate-50">
        <article className="md-preview prose-doc max-w-none mx-auto bg-white px-8 py-6 rounded shadow-sm border border-slate-200">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {data.markdown}
          </ReactMarkdown>
        </article>
      </div>

      {/* Footer actions */}
      <div className="shrink-0 px-6 py-3 border-t border-slate-200 bg-white flex items-center justify-end gap-2">
        <button
          onClick={onClose}
          className="px-3 py-1.5 text-xs font-medium text-slate-600 border border-slate-300 rounded-md hover:bg-slate-50"
        >
          Close
        </button>
        <button
          onClick={onDownload}
          className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold text-white rounded-md transition-colors"
          style={{ background: "#0d9488" }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "#0f766e")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "#0d9488")}
        >
          <Download size={14} strokeWidth={2.25} />
          Download .md
        </button>
      </div>
    </>
  );
}
