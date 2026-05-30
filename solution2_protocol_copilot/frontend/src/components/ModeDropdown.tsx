import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown } from "lucide-react";
import { useModeStore, type LLMMode } from "@/stores/modeStore";

interface ModeOption {
  value: LLMMode;
  label: string;
  description: string;
}

const MODE_OPTIONS: ModeOption[] = [
  { value: "mock",   label: "MOCK",   description: "Template responses, no LLM" },
  { value: "fake",   label: "FAKE",   description: "Deterministic realistic responses" },
  { value: "cached", label: "CACHED", description: "Replay captured real responses" },
  { value: "live",   label: "LIVE",   description: "Real Azure OpenAI calls" },
];

/**
 * Runtime mode toggle in the navy app chrome.
 * Reads + writes useModeStore; every API call picks up the new mode on its
 * next request via the X-LLM-Mode header attached in lib/api.ts:apiFetch.
 * Hidden when ?recording=true (see AppChrome).
 */
export default function ModeDropdown() {
  const selectedMode = useModeStore((s) => s.selectedMode);
  const setMode = useModeStore((s) => s.setMode);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Click outside + Escape close
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex items-center gap-1.5 rounded-full bg-slate-700/60 px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-white hover:bg-slate-600/80 transition-colors"
      >
        <span className="text-slate-400">MODE:</span>
        <span>{selectedMode}</span>
        <ChevronDown size={12} strokeWidth={2.5}
          className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            key="mode-panel"
            role="listbox"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 top-full mt-1.5 w-64 rounded-lg border border-slate-200 bg-white shadow-xl z-50 overflow-hidden"
          >
            {MODE_OPTIONS.map((option) => {
              const active = selectedMode === option.value;
              return (
                <button
                  key={option.value}
                  role="option"
                  aria-selected={active}
                  onClick={() => { setMode(option.value); setOpen(false); }}
                  className={`w-full flex items-start justify-between gap-2 px-4 py-2.5 text-left transition-colors ${
                    active ? "bg-teal-50" : "hover:bg-slate-50"
                  }`}
                >
                  <div className="min-w-0">
                    <div className="text-xs font-bold text-slate-900 tracking-wider">
                      {option.label}
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5 leading-snug">
                      {option.description}
                    </div>
                  </div>
                  {active && <Check size={14} strokeWidth={2.5} className="text-teal-600 mt-1 shrink-0" />}
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
