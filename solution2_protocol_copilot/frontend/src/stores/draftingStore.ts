import { create } from "zustand";

export interface ProtocolGap {
  gap_id: string;
  name: string;
  category: string;
  rationale: string;
  suggested_section: string;
  suggested_section_id: string;
  draft_topic: string;
  regulatory_reference: string | null;
  severity: string;
}

export interface GapDetectionResponse {
  protocol_id: string;
  checklist_version: string;
  gaps_detected: ProtocolGap[];
  detected_at: string;
}

interface DraftingState {
  gapsDetected: ProtocolGap[];
  gapsLoading: boolean;
  gapPanelOpen: boolean;
  setGaps: (gaps: ProtocolGap[]) => void;
  setGapsLoading: (loading: boolean) => void;
  setGapPanelOpen: (open: boolean) => void;
  removeGap: (gapId: string) => void;
}

export const useDraftingStore = create<DraftingState>((set) => ({
  gapsDetected: [],
  gapsLoading: false,
  gapPanelOpen: false,
  setGaps: (gaps) => set({ gapsDetected: gaps }),
  setGapsLoading: (loading) => set({ gapsLoading: loading }),
  setGapPanelOpen: (open) => set({ gapPanelOpen: open }),
  removeGap: (gapId) =>
    set((state) => ({
      gapsDetected: state.gapsDetected.filter((g) => g.gap_id !== gapId),
    })),
}));
