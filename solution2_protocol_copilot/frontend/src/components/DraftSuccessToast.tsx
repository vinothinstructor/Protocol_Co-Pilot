import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, X } from "lucide-react";

interface Props {
  message: string | null;
  onDismiss: () => void;
}

export default function DraftSuccessToast({ message, onDismiss }: Props) {
  useEffect(() => {
    if (!message) return;
    const id = setTimeout(onDismiss, 4000);
    return () => clearTimeout(id);
  }, [message, onDismiss]);

  return (
    <AnimatePresence>
      {message && (
        <motion.div
          key="draft-success-toast"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 10 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="fixed z-50 rounded-lg shadow-lg border border-slate-200 bg-white overflow-hidden"
          style={{ right: "1.5rem", bottom: "8rem", width: 340 }}
        >
          <div className="h-1 w-full" style={{ background: "#16a34a" }} />
          <div className="px-4 pt-3 pb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 size={15} style={{ color: "#16a34a", flexShrink: 0 }} />
              <span className="text-xs text-slate-700">{message}</span>
            </div>
            <button
              onClick={onDismiss}
              className="text-slate-400 hover:text-slate-600 transition-colors shrink-0"
              aria-label="Dismiss"
            >
              <X size={13} />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
