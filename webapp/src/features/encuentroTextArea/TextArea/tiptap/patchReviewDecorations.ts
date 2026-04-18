import { Extension } from "@tiptap/core";
import type { Editor } from "@tiptap/react";
import type { Node as ProseMirrorNode } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { CopilotPatchResponse } from "@/features/copilotChat/types";

export type PatchReviewResolutionStatus =
  | "resolved"
  | "missing"
  | "ambiguous"
  | "unsupported";

export type PatchReviewResolution = {
  patch: CopilotPatchResponse;
  status: PatchReviewResolutionStatus;
  from: number | null;
  to: number | null;
  insertPos: number | null;
  reason: string | null;
};

type PatchReviewPluginState = {
  decorations: DecorationSet;
  resolutions: PatchReviewResolution[];
};

type PatchReviewPluginMeta = {
  resolutions: PatchReviewResolution[];
  selectedPatchId: string | null;
};

type PatchReviewExtensionOptions = {
  onSelectPatch?: (patchId: string) => void;
  onApprovePatch?: (patchId: string) => void;
  onRejectPatch?: (patchId: string) => void;
};

export const patchReviewPluginKey = new PluginKey<PatchReviewPluginState>(
  "patch-review-decorations",
);

function normalizeText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function buildTextIndex(doc: ProseMirrorNode): { text: string; positions: number[] } {
  let text = "";
  const positions: number[] = [];

  doc.descendants((node, pos) => {
    if (!node.isText || !node.text) {
      return true;
    }

    for (let index = 0; index < node.text.length; index += 1) {
      positions[text.length + index] = pos + index;
    }
    text += node.text;
    positions[text.length] = pos + node.text.length;
    return true;
  });

  return { text, positions };
}

function buildNormalizedIndex(value: string): {
  normalized: string;
  normalizedToOriginal: number[];
} {
  let normalized = "";
  const normalizedToOriginal: number[] = [];
  let previousWasWhitespace = false;

  for (let index = 0; index < value.length; index += 1) {
    const char = value[index];
    if (/\s/.test(char)) {
      if (!previousWasWhitespace && normalized.length > 0) {
        normalizedToOriginal[normalized.length] = index;
        normalized += " ";
      }
      previousWasWhitespace = true;
      continue;
    }

    normalizedToOriginal[normalized.length] = index;
    normalized += char;
    previousWasWhitespace = false;
  }

  if (normalized.endsWith(" ")) {
    normalized = normalized.slice(0, -1);
    normalizedToOriginal.pop();
  }

  return { normalized, normalizedToOriginal };
}

function uniqueRanges(ranges: Array<{ start: number; end: number }>) {
  const seen = new Set<string>();
  return ranges.filter((range) => {
    const key = `${range.start}:${range.end}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function findTextRanges(haystack: string, needle: string) {
  const target = needle.trim();
  if (!target) {
    return [];
  }

  const exactRanges: Array<{ start: number; end: number }> = [];
  let cursor = 0;
  while (cursor <= haystack.length) {
    const index = haystack.indexOf(target, cursor);
    if (index === -1) {
      break;
    }
    exactRanges.push({ start: index, end: index + target.length });
    cursor = index + 1;
  }

  if (exactRanges.length > 0) {
    return uniqueRanges(exactRanges);
  }

  const normalizedNeedle = normalizeText(target);
  if (!normalizedNeedle) {
    return [];
  }

  const { normalized, normalizedToOriginal } = buildNormalizedIndex(haystack);
  const normalizedRanges: Array<{ start: number; end: number }> = [];
  cursor = 0;
  while (cursor <= normalized.length) {
    const index = normalized.indexOf(normalizedNeedle, cursor);
    if (index === -1) {
      break;
    }

    const originalStart = normalizedToOriginal[index];
    const originalEnd =
      (normalizedToOriginal[index + normalizedNeedle.length - 1] ?? originalStart) +
      1;
    normalizedRanges.push({ start: originalStart, end: originalEnd });
    cursor = index + 1;
  }

  return uniqueRanges(normalizedRanges);
}

function contextMatches(
  text: string,
  range: { start: number; end: number },
  patch: CopilotPatchResponse,
) {
  const prefix = patch.anchor.prefixText;
  const suffix = patch.anchor.suffixText;
  const before = normalizeText(text.slice(Math.max(0, range.start - 240), range.start));
  const after = normalizeText(text.slice(range.end, range.end + 240));

  if (prefix && !before.endsWith(normalizeText(prefix))) {
    return false;
  }

  if (suffix && !after.startsWith(normalizeText(suffix))) {
    return false;
  }

  return true;
}

function chooseRange(
  text: string,
  patch: CopilotPatchResponse,
): { start: number; end: number; reason: string | null } | null {
  const anchorText = patch.anchor.exactText?.trim();
  const primaryRanges = anchorText ? findTextRanges(text, anchorText) : [];
  const narrowedPrimary = primaryRanges.filter((range) =>
    contextMatches(text, range, patch),
  );
  const primaryCandidates =
    narrowedPrimary.length > 0 ? narrowedPrimary : primaryRanges;

  if (primaryCandidates.length === 1) {
    return { ...primaryCandidates[0], reason: null };
  }

  if (primaryCandidates.length > 1) {
    return {
      ...primaryCandidates[0],
      reason: "El anchor coincide en varias ubicaciones.",
    };
  }

  const fallbackRanges = patch.oldText ? findTextRanges(text, patch.oldText) : [];
  if (fallbackRanges.length === 1) {
    return { ...fallbackRanges[0], reason: null };
  }

  if (fallbackRanges.length > 1) {
    return {
      ...fallbackRanges[0],
      reason: "El texto anterior coincide en varias ubicaciones.",
    };
  }

  return null;
}

function toEditorRange(
  positions: number[],
  range: { start: number; end: number },
) {
  const from = positions[range.start];
  const to = positions[range.end] ?? positions[Math.max(range.end - 1, range.start)] + 1;

  if (typeof from !== "number" || typeof to !== "number" || from >= to) {
    return null;
  }

  return { from, to };
}

export function resolvePatchReviewPatches(
  editor: Editor,
  patches: CopilotPatchResponse[],
): PatchReviewResolution[] {
  const { text, positions } = buildTextIndex(editor.state.doc);

  return patches.map((patch) => {
    if (patch.normalizedOperationType === "replace_span" && patch.operationType === "rewrite_document") {
      return {
        patch,
        status: "unsupported",
        from: null,
        to: null,
        insertPos: null,
        reason: "Cambio de documento completo.",
      };
    }

    const chosenRange = chooseRange(text, patch);
    if (!chosenRange) {
      return {
        patch,
        status: "missing",
        from: null,
        to: null,
        insertPos: null,
        reason: "No se pudo ubicar este cambio en el documento visible.",
      };
    }

    const editorRange = toEditorRange(positions, chosenRange);
    if (!editorRange) {
      return {
        patch,
        status: "missing",
        from: null,
        to: null,
        insertPos: null,
        reason: "No se pudo mapear el cambio a una posicion del editor.",
      };
    }

    const insertPos =
      patch.normalizedOperationType === "insert_before"
        ? editorRange.from
        : patch.normalizedOperationType === "insert_after"
          ? editorRange.to
          : null;

    return {
      patch,
      status: chosenRange.reason ? "ambiguous" : "resolved",
      from: editorRange.from,
      to: editorRange.to,
      insertPos,
      reason: chosenRange.reason,
    };
  });
}

function operationActionLabel(operationType: string) {
  if (operationType === "delete_span") {
    return "Eliminar";
  }
  if (operationType === "insert_before" || operationType === "insert_after") {
    return "Agregar";
  }
  return "Cambiar por";
}

function appendInlineActionButton(
  container: HTMLElement,
  patchId: string,
  action: "approve" | "reject",
) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `patch-review-inline-action patch-review-inline-action-${action}`;
  button.dataset.patchId = patchId;
  button.dataset.patchReviewAction = action;
  button.textContent = action === "approve" ? "✓" : "×";
  button.title = action === "approve" ? "Aceptar cambio" : "Rechazar cambio";
  container.appendChild(button);
}

function createInlineDiffWidget(
  resolution: PatchReviewResolution,
  isSelected: boolean,
) {
  const { patch } = resolution;
  const container = document.createElement("span");
  container.className = [
    "patch-review-inline-diff",
    `patch-review-inline-diff-${patch.normalizedOperationType}`,
    isSelected ? "patch-review-inline-diff-selected" : "",
  ]
    .filter(Boolean)
    .join(" ");
  container.dataset.patchId = patch.id;

  if (resolution.reason) {
    container.title = resolution.reason;
  }

  if (patch.status !== "pending") {
    const status = document.createElement("span");
    status.className = `patch-review-inline-status patch-review-inline-status-${patch.status}`;
    status.textContent = patch.status === "accepted" ? "Aceptado" : "Rechazado";
    container.appendChild(status);
    return container;
  }

  if (patch.newText && patch.normalizedOperationType !== "delete_span") {
    const label = document.createElement("span");
    label.className = "patch-review-inline-label";
    label.textContent = operationActionLabel(patch.normalizedOperationType);
    container.appendChild(label);

    const addition = document.createElement("span");
    addition.className = "patch-review-inline-addition";
    addition.textContent = patch.newText;
    container.appendChild(addition);
  } else if (patch.normalizedOperationType === "delete_span") {
    const label = document.createElement("span");
    label.className = "patch-review-inline-label patch-review-inline-label-delete";
    label.textContent = "Eliminar";
    container.appendChild(label);
  }

  const actions = document.createElement("span");
  actions.className = "patch-review-inline-actions";
  appendInlineActionButton(actions, patch.id, "approve");
  appendInlineActionButton(actions, patch.id, "reject");
  container.appendChild(actions);

  return container;
}

function buildDecorations(
  doc: ProseMirrorNode,
  resolutions: PatchReviewResolution[],
  selectedPatchId: string | null,
) {
  const decorations: Decoration[] = [];

  for (const resolution of resolutions) {
    if (resolution.from == null || resolution.to == null) {
      continue;
    }

    const { patch } = resolution;
    const isSelected = patch.id === selectedPatchId;
    const classes = [
      "patch-review-highlight",
      `patch-review-highlight-${patch.normalizedOperationType}`,
      `patch-review-highlight-${patch.status}`,
      resolution.status === "ambiguous" ? "patch-review-highlight-ambiguous" : "",
      isSelected ? "patch-review-highlight-selected" : "",
    ]
      .filter(Boolean)
      .join(" ");

    decorations.push(
      Decoration.inline(resolution.from, resolution.to, {
        class: classes,
        "data-patch-id": patch.id,
      }),
    );

    const widgetPosition = resolution.insertPos ?? resolution.to;
    const widgetSide = patch.normalizedOperationType === "insert_before" ? -1 : 1;
    decorations.push(
      Decoration.widget(
        widgetPosition,
        () => createInlineDiffWidget(resolution, isSelected),
        { side: widgetSide },
      ),
    );
  }

  return DecorationSet.create(doc, decorations);
}

export function setPatchReviewDecorations(
  editor: Editor,
  resolutions: PatchReviewResolution[],
  selectedPatchId: string | null,
) {
  const meta: PatchReviewPluginMeta = { resolutions, selectedPatchId };
  editor.view.dispatch(editor.state.tr.setMeta(patchReviewPluginKey, meta));
}

export const PatchReviewDecorationExtension =
  Extension.create<PatchReviewExtensionOptions>({
    name: "patchReviewDecorations",

    addOptions() {
      return {
        onSelectPatch: undefined,
      };
    },

    addProseMirrorPlugins() {
      const onSelectPatch = this.options.onSelectPatch;
      const onApprovePatch = this.options.onApprovePatch;
      const onRejectPatch = this.options.onRejectPatch;

      return [
        new Plugin<PatchReviewPluginState>({
          key: patchReviewPluginKey,
          state: {
            init: () => ({
              decorations: DecorationSet.empty,
              resolutions: [],
            }),
            apply: (transaction, previous, _oldState, newState) => {
              const meta = transaction.getMeta(patchReviewPluginKey) as
                | PatchReviewPluginMeta
                | undefined;

              if (meta) {
                return {
                  decorations: buildDecorations(
                    newState.doc,
                    meta.resolutions,
                    meta.selectedPatchId,
                  ),
                  resolutions: meta.resolutions,
                };
              }

              if (transaction.docChanged) {
                return {
                  ...previous,
                  decorations: previous.decorations.map(
                    transaction.mapping,
                    transaction.doc,
                  ),
                };
              }

              return previous;
            },
          },
          props: {
            decorations: (state) =>
              patchReviewPluginKey.getState(state)?.decorations ??
              DecorationSet.empty,
            handleClick: (_view, _pos, event) => {
              const target = event.target as HTMLElement | null;
              const actionElement = target?.closest<HTMLElement>(
                "[data-patch-review-action]",
              );
              const action = actionElement?.dataset.patchReviewAction;
              const actionPatchId = actionElement?.dataset.patchId;
              if (actionPatchId && action === "approve") {
                onApprovePatch?.(actionPatchId);
                return true;
              }
              if (actionPatchId && action === "reject") {
                onRejectPatch?.(actionPatchId);
                return true;
              }

              const patchElement = target?.closest<HTMLElement>("[data-patch-id]");
              const patchId = patchElement?.dataset.patchId;
              if (!patchId) {
                return false;
              }

              onSelectPatch?.(patchId);
              return true;
            },
          },
        }),
      ];
    },
  });
