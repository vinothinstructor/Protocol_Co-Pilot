import { createPortal } from "react-dom";
import { motion } from "framer-motion";

interface Props {
  delta: number;        // e.g. -18
  fromRect: DOMRect;   // Accept button bounding rect
  toRect: DOMRect;     // Score element bounding rect
  onComplete: () => void;
}

/**
 * Renders a floating delta chip that travels in a straight line from the
 * Accept button (right panel) to the risk score (status bar), making the
 * cause-and-effect of accepting a fix visually explicit.
 * Rendered via a portal so it floats above all overflow:hidden containers.
 */
export default function FloatingDeltaChip({ delta, fromRect, toRect, onComplete }: Props) {
  const fromX = fromRect.left + fromRect.width / 2;
  const fromY = fromRect.top + fromRect.height / 2;
  const toX = toRect.left + toRect.width / 2;
  const toY = toRect.top + toRect.height / 2;

  // Direct path: travel straight from the Accept button to the score. A gentle
  // mid-flight scale-up draws the eye without the "bounce off a wall" detour.
  return createPortal(
    <motion.div
      style={{
        position: "fixed",
        left: fromX - 28,
        top: fromY - 16,
        zIndex: 9999,
        pointerEvents: "none",
        originX: "50%",
        originY: "50%",
      }}
      initial={{ opacity: 1, scale: 1, x: 0, y: 0 }}
      animate={{
        // Travel to the score over the first 70% of the duration at full opacity,
        // ARRIVE, then fade out in place at the score. The chip visibly reaches
        // the score before disappearing (no mid-flight fade).
        x: [0, toX - fromX, toX - fromX],
        y: [0, toY - fromY, toY - fromY],
        scale: [1, 1.12, 1],
        opacity: [1, 1, 0],
      }}
      transition={{
        duration: 0.85,
        times: [0, 0.7, 1],
        ease: ["easeInOut", "easeIn"],
      }}
      onAnimationComplete={onComplete}
    >
      <span
        className="inline-flex items-center justify-center font-bold text-white text-sm rounded-full shadow-lg"
        style={{
          padding: "4px 11px",
          background: "linear-gradient(135deg, #dc2626 0%, #0d9488 100%)",
          minWidth: 56,
          letterSpacing: "-0.02em",
          whiteSpace: "nowrap",
        }}
      >
        {delta}%
      </span>
    </motion.div>,
    document.body
  );
}
