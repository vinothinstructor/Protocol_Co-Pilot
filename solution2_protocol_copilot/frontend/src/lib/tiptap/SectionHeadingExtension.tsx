/**
 * Custom heading extension that adds a "+ Generate clause" button
 * to sections 4, 5, and 6 (the clause-list sections) on hover.
 * All other headings render identically to the default heading.
 */
import React, { useState } from "react";

// Augment TipTap's HeadingOptions type to include the draft-click callback
declare module "@tiptap/extension-heading" {
  interface HeadingOptions {
    onDraftClick?: (sectionId: string) => void;
  }
}
import { Heading } from "@tiptap/extension-heading";
import {
  ReactNodeViewRenderer,
  NodeViewWrapper,
  NodeViewContent,
  type NodeViewRendererProps,
} from "@tiptap/react";
import { PlusCircle } from "lucide-react";

const CLAUSE_SECTION_NUMBERS = new Set([4, 5, 6]);

function HeadingNodeView({ node, extension }: NodeViewRendererProps) {
  const [hovered, setHovered] = useState(false);
  const level = node.attrs.level as number;

  const text = node.textContent;
  const match = text.match(/^(\d+)\./);
  const sectionNum = match ? parseInt(match[1]) : 0;
  const showButton = level === 2 && CLAUSE_SECTION_NUMBERS.has(sectionNum);
  const sectionId = `sec_${sectionNum}`;

  const onDraftClick = (
    extension.options as { onDraftClick?: (sectionId: string) => void }
  ).onDraftClick;

  // Tag for the heading element
  const HeadingTag = `h${level}` as React.ElementType;

  if (!showButton || !onDraftClick) {
    return (
      <NodeViewWrapper as={HeadingTag}>
        <NodeViewContent />
      </NodeViewWrapper>
    );
  }

  return (
    <NodeViewWrapper
      as="div"
      style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <NodeViewContent as={HeadingTag} style={{ flex: 1, margin: 0 }} />
      <button
        contentEditable={false}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onDraftClick(sectionId);
        }}
        title={`Generate clause for Section ${sectionNum}`}
        aria-label={`Generate clause for Section ${sectionNum}`}
        style={{
          opacity: hovered ? 1 : 0,
          transition: "opacity 0.15s",
          color: "#0d9488",
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: "2px 4px",
          display: "flex",
          alignItems: "center",
          flexShrink: 0,
          marginLeft: 8,
          userSelect: "none",
        }}
      >
        <PlusCircle size={16} strokeWidth={2} />
      </button>
    </NodeViewWrapper>
  );
}

export const SectionHeadingExtension = Heading.extend({
  addOptions() {
    return {
      ...this.parent?.(),
      onDraftClick: undefined as ((sectionId: string) => void) | undefined,
    };
  },
  addNodeView() {
    return ReactNodeViewRenderer(HeadingNodeView);
  },
});
