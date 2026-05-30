import { Circle } from "lucide-react";
import ModeDropdown from "./ModeDropdown";

interface AppChromeProps {
  protocolId?: string;
  version?: string;
}

// Read once at module load — flips with ?recording=true in the URL.
// Used to hide the MODE indicator for demo recording so "mock" doesn't leak
// into screenshots/video. Toggleable without restarting the dev server.
const isRecording =
  typeof window !== "undefined" &&
  new URLSearchParams(window.location.search).get("recording") === "true";

export default function AppChrome({
  protocolId = "DIABETES-2026-PH3",
  version = "v3.2",
}: AppChromeProps) {
  return (
    <header className="flex items-center justify-between px-6 py-3 bg-navy-800 text-white shadow-md shrink-0">
      <div className="flex items-center gap-2">
        <Circle size={10} className="fill-teal-400 text-teal-400" />
        <span className="font-semibold text-sm tracking-wide">
          IQVIA&nbsp;·&nbsp;Protocol Co-Pilot
        </span>
      </div>

      <div className="text-sm text-slate-300 font-mono">
        {protocolId}.docx&nbsp;·&nbsp;{version}
      </div>

      {!isRecording ? (
        <ModeDropdown />
      ) : (
        // Empty spacer so flex spacing matches the visible-dropdown layout
        <div className="w-0" aria-hidden="true" />
      )}
    </header>
  );
}
