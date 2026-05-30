import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

// NOTE: StrictMode intentionally not used.
// In dev, StrictMode double-invokes effects, which causes the live-scoring hook's
// editor.on("update") subscription to be wired then immediately torn down. The
// teardown clears any pending debounce timer, so the timer never fires. Live
// editing requires the subscription to remain stable across the typing burst.
createRoot(document.getElementById("root")!).render(<App />);
