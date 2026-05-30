import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, X } from "lucide-react";
import { useFeasibilityStore } from "@/stores/feasibilityStore";
import { useModeStore } from "@/stores/modeStore";

export default function FeasibilityErrorToast() {
  const { feasibilityError, setFeasibilityError } = useFeasibilityStore();
  const { setMode } = useModeStore();

  // Auto-dismiss after 8s
  useEffect(() => {
    if (!feasibilityError) return;
    const id = setTimeout(() => setFeasibilityError(null), 8000);
    return () => clearTimeout(id);
  }, [feasibilityError, setFeasibilityError]);

  const handleSwitchToCached = () => {
    setMode("cached");
    setFeasibilityError(null);
  };

  return (
    <AnimatePresence>
      {feasibilityError && (
        <motion.div
          key="feasibility-error-toast"
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="fixed z-50 rounded-lg shadow-lg border overflow-hidden"
          style={{
            right: "1.5rem",
            top: "4rem",
            width: 360,
            borderColor: "rgba(220,38,38,0.25)",
            background: "#fff",
          }}
          role="alert"
          aria-live="assertive"
        >
          {/* Red top accent */}
          <div className="h-1 w-full" style={{ background: "#dc2626" }} />

          <div className="px-4 pt-3 pb-3.5">
            {/* Header */}
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="flex items-center gap-2">
                <AlertTriangle
                  size={15}
                  strokeWidth={2.25}
                  style={{ color: "#dc2626", flexShrink: 0, marginTop: 1 }}
                />
                <span
                  className="text-[11px] font-bold tracking-widest uppercase"
                  style={{ color: "#dc2626" }}
                >
                  Feasibility unavailable
                </span>
              </div>
              <button
                onClick={() => setFeasibilityError(null)}
                className="text-slate-400 hover:text-slate-600 transition-colors shrink-0"
                aria-label="Dismiss"
              >
                <X size={14} />
              </button>
            </div>

            {/* Error detail */}
            <p className="text-xs text-slate-600 leading-relaxed mb-3">
              {feasibilityError}
            </p>

            {/* Switch to cached action */}
            <button
              onClick={handleSwitchToCached}
              className="text-xs font-semibold rounded px-3 py-1.5 transition-colors text-white"
              style={{ background: "#0d9488" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#0f766e")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "#0d9488")}
            >
              Switch to CACHED
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
