import { StarterKit } from "@tiptap/starter-kit";
import { Paragraph } from "@tiptap/extension-paragraph";
import { ListItem } from "@tiptap/extension-list-item";
import { RiskDecorationExtension } from "./RiskDecorationPlugin";
import { BlockIdAssignerExtension } from "./BlockIdPlugin";
import { SectionHeadingExtension } from "./SectionHeadingExtension";
import type { Extensions } from "@tiptap/react";

// Extend Paragraph to carry data-block-id so decorations can attach
const BlockParagraph = Paragraph.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      blockId: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-block-id"),
        renderHTML: (attributes) => {
          if (!attributes.blockId) return {};
          return { "data-block-id": attributes.blockId };
        },
      },
    };
  },
});

// Extend ListItem to carry data-block-id on clause items
const BlockListItem = ListItem.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      blockId: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-block-id"),
        renderHTML: (attributes) => {
          if (!attributes.blockId) return {};
          return { "data-block-id": attributes.blockId };
        },
      },
    };
  },
});

/**
 * Build the TipTap extension array for the protocol editor.
 * Pass `onSectionDraftClick` to enable the "+ Generate clause" button
 * on sections 4, 5, and 6. Omit it to render plain headings.
 */
export function buildProtocolExtensions(
  onSectionDraftClick?: (sectionId: string) => void
): Extensions {
  return [
    StarterKit.configure({
      paragraph: false,      // replaced by BlockParagraph
      listItem: false,       // replaced by BlockListItem
      heading: false,        // replaced by SectionHeadingExtension
      bulletList: { keepMarks: true },
      // Phase 6: enable bold/italic for the BubbleMenu toolbar
      strike: false,
      code: false,
      codeBlock: false,
      blockquote: false,
      horizontalRule: false,
    }),
    BlockParagraph,
    BlockListItem,
    BlockIdAssignerExtension,
    RiskDecorationExtension,
    SectionHeadingExtension.configure({
      levels: [1, 2, 3],
      onDraftClick: onSectionDraftClick,
    }),
  ];
}

// Keep the static export for any code that doesn't need drafting (backwards compat)
export const protocolExtensions = buildProtocolExtensions();
