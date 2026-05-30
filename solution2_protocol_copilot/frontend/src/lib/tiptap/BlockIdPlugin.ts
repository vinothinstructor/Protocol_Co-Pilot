/**
 * Auto-assign stable block_ids to newly-created paragraph / listItem nodes.
 *
 * When ProseMirror creates a node from a transaction (e.g., the user types Enter
 * to start a new paragraph), the `blockId` attribute defaults to null. This
 * appendTransaction plugin scans for such nodes and assigns a fresh
 * `gen_<unix>_<rand4>` id in a follow-up transaction.
 *
 * Why Option B (appendTransaction) over Option A (function-as-default):
 * TipTap's addAttributes defaults are evaluated once at schema construction,
 * not per-node, so a function default would return the SAME id for every node.
 * Doing it post-hoc in a plugin is unambiguous and ProseMirror-idiomatic.
 */

import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Extension } from "@tiptap/react";

const blockIdPluginKey = new PluginKey("blockIdAssigner");

const TARGET_NODE_TYPES = new Set(["paragraph", "listItem"]);

function genBlockId(): string {
  const unix = Math.floor(Date.now() / 1000);
  const rand = Math.floor(Math.random() * 0xffff)
    .toString(16)
    .padStart(4, "0");
  return `gen_${unix}_${rand}`;
}

const blockIdPlugin = new Plugin({
  key: blockIdPluginKey,

  appendTransaction(_transactions, _oldState, newState) {
    const tr = newState.tr;
    let modified = false;
    const seenIds = new Set<string>();

    newState.doc.descendants((node, pos, parent) => {
      if (!TARGET_NODE_TYPES.has(node.type.name)) return;

      // Skip paragraphs nested inside a listItem — the parent listItem already
      // carries the block_id; the inner paragraph is just a text container.
      // Without this guard, editing a clause's text would change the inner
      // paragraph's gen_ id (not the listItem's blk_ id), so the live-scoring
      // pipeline would score a stray gen_ instead of updating the listItem.
      if (node.type.name === "paragraph" && parent && parent.type.name === "listItem") {
        return;
      }

      const existing = node.attrs.blockId as string | null;
      if (!existing || seenIds.has(existing)) {
        const newId = genBlockId();
        tr.setNodeMarkup(pos, undefined, { ...node.attrs, blockId: newId });
        seenIds.add(newId);
        modified = true;
      } else {
        seenIds.add(existing);
      }
    });

    return modified ? tr : null;
  },
});

export const BlockIdAssignerExtension = Extension.create({
  name: "blockIdAssigner",
  addProseMirrorPlugins() {
    return [blockIdPlugin];
  },
});
