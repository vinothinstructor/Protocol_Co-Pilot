import { useState, useRef, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X, Loader2, PenLine } from "lucide-react";

interface Props {
  open: boolean;
  sectionId: string | null;
  onClose: () => void;
  onGenerate: (topic: string, sectionId: string) => Promise<void>;
}

const PRESET_CHIPS = [
  "Severe hypoglycemia exclusion",
  "HbA1c upper bound exclusion",
  "Cardiovascular history exclusion",
  "Renal function inclusion criterion",
  "Pregnancy/contraception requirement",
];

export default function DraftClausePopover({ open, sectionId, onClose, onGenerate }: Props) {
  const [generating, setGenerating] = useState(false);
  const [freeform, setFreeform] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input when popover opens
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setFreeform("");
      setGenerating(false);
    }
  }, [open]);

  const handleGenerate = async (topic: string) => {
    if (!sectionId || !topic.trim() || generating) return;
    setGenerating(true);
    try {
      await onGenerate(topic.trim(), sectionId);
      // onGenerate closes the popover on success; on error it stays open
    } catch {
      // Error surfaced by onGenerate via the error toast; stay open for retry
    } finally {
      setGenerating(false);
    }
  };

  const handleChipClick = (topic: string) => {
    if (generating) return;
    handleGenerate(topic);
  };

  const handleFreeformGenerate = () => {
    if (freeform.trim()) handleGenerate(freeform);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && freeform.trim()) handleFreeformGenerate();
    if (e.key === "Escape") onClose();
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={onClose}
            aria-hidden="true"
          />

          {/* Popover */}
          <motion.div
            key="draft-popover"
            initial={{ opacity: 0, scale: 0.96, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -8 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="fixed z-50 bg-white rounded-xl shadow-2xl border border-slate-200"
            style={{
              width: 380,
              top: "50%",
              left: "60%",
              transform: "translate(-50%, -50%)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-start justify-between px-5 pt-4 pb-3 border-b border-slate-100">
              <div>
                <div className="flex items-center gap-2">
                  <PenLine size={14} style={{ color: "#0d9488" }} strokeWidth={2.25} />
                  <h3 className="text-sm font-bold" style={{ color: "#1a2744" }}>
                    Generate a clause
                  </h3>
                </div>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Choose a topic or describe what you need
                </p>
              </div>
              <button
                onClick={onClose}
                disabled={generating}
                className="text-slate-400 hover:text-slate-600 transition-colors disabled:opacity-40"
                aria-label="Cancel"
              >
                <X size={15} />
              </button>
            </div>

            {/* Preset chips */}
            <div className="px-5 pt-3 pb-2">
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
                Common clauses
              </p>
              <div className="flex flex-wrap gap-2">
                {PRESET_CHIPS.map((chip) => (
                  <button
                    key={chip}
                    onClick={() => handleChipClick(chip)}
                    disabled={generating}
                    className="text-[11px] font-medium px-2.5 py-1 rounded-full border transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    style={{
                      borderColor: "#0d9488",
                      color: "#0d9488",
                      background: "rgba(13,148,136,0.05)",
                    }}
                    onMouseEnter={(e) => {
                      if (!generating) {
                        e.currentTarget.style.background = "rgba(13,148,136,0.12)";
                      }
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = "rgba(13,148,136,0.05)";
                    }}
                  >
                    {chip}
                  </button>
                ))}
              </div>
            </div>

            {/* Divider */}
            <div className="mx-5 my-2 border-t border-slate-100" />

            {/* Freeform input */}
            <div className="px-5 pb-4">
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
                Or type your own topic
              </p>
              <div className="flex gap-2">
                <input
                  ref={inputRef}
                  type="text"
                  value={freeform}
                  onChange={(e) => setFreeform(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={generating}
                  placeholder="e.g., patient must have diabetes for at least 2 years"
                  className="flex-1 text-xs border border-slate-200 rounded-md px-3 py-2 outline-none focus:border-teal-400 focus:ring-1 focus:ring-teal-200 disabled:opacity-40 disabled:bg-slate-50"
                />
                <button
                  onClick={handleFreeformGenerate}
                  disabled={generating || !freeform.trim()}
                  className="text-xs font-semibold px-3 py-2 rounded-md text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
                  style={{ background: "#0d9488" }}
                  onMouseEnter={(e) => {
                    if (!generating && freeform.trim()) e.currentTarget.style.background = "#0f766e";
                  }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = "#0d9488"; }}
                >
                  {generating ? (
                    <>
                      <Loader2 size={12} className="animate-spin" />
                      Drafting…
                    </>
                  ) : (
                    "Generate"
                  )}
                </button>
              </div>
            </div>

            {/* Generating overlay on chips */}
            {generating && (
              <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-white/70">
                <div className="flex items-center gap-2 text-sm text-slate-600">
                  <Loader2 size={16} className="animate-spin text-teal-600" />
                  <span>Drafting clause…</span>
                </div>
              </div>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
