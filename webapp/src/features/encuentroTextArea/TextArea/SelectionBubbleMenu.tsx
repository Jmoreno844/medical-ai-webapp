import React, { useCallback, useEffect, useRef, useState } from "react";
import { BubbleMenu } from "@tiptap/react/menus";
import { useEditorState, type Editor } from "@tiptap/react";
import { isTextSelection } from "@tiptap/core";
import { Bold, Italic, Underline, Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";

type SelectionBubbleMenuProps = {
  editor: Editor | null;
  onCopy?: () => void;
};

type FormatButtonProps = {
  label: string;
  isActive?: boolean;
  onClick: () => void;
  children: React.ReactNode;
};

const FormatButton: React.FC<FormatButtonProps> = ({
  label,
  isActive = false,
  onClick,
  children,
}) => (
  <button
    type="button"
    aria-label={label}
    title={label}
    // Evita que el clic robe la selección de texto del editor.
    onMouseDown={(event) => event.preventDefault()}
    onClick={onClick}
    className={cn(
      "flex items-center justify-center rounded p-1.5 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900",
      isActive && "bg-slate-200 text-slate-900",
    )}
  >
    {children}
  </button>
);

const SelectionBubbleMenu: React.FC<SelectionBubbleMenuProps> = ({
  editor,
  onCopy,
}) => {
  const [copied, setCopied] = useState(false);
  const copiedTimerRef = useRef<number | null>(null);

  const editorState = useEditorState({
    editor,
    selector: ({ editor }) => ({
      isBold: editor?.isActive("bold") ?? false,
      isItalic: editor?.isActive("italic") ?? false,
      isUnderline: editor?.isActive("underline") ?? false,
      isEditable: editor?.isEditable ?? false,
    }),
  });

  useEffect(() => {
    return () => {
      if (copiedTimerRef.current !== null) {
        window.clearTimeout(copiedTimerRef.current);
      }
    };
  }, []);

  const handleCopySelection = useCallback(() => {
    if (!editor) {
      return;
    }
    const { from, to } = editor.state.selection;
    const text = editor.state.doc.textBetween(from, to, "\n");
    if (!text) {
      return;
    }

    void navigator.clipboard
      .writeText(text)
      .then(() => {
        onCopy?.();
        setCopied(true);
        if (copiedTimerRef.current !== null) {
          window.clearTimeout(copiedTimerRef.current);
        }
        copiedTimerRef.current = window.setTimeout(() => {
          setCopied(false);
          copiedTimerRef.current = null;
        }, 1200);
      })
      .catch(() => {
        // Si el portapapeles no está disponible, no bloqueamos al usuario.
      });
  }, [editor, onCopy]);

  if (!editor) {
    return null;
  }

  const isBold = editorState?.isBold ?? false;
  const isItalic = editorState?.isItalic ?? false;
  const isUnderline = editorState?.isUnderline ?? false;
  const isEditable = editorState?.isEditable ?? false;

  return (
    <BubbleMenu
      editor={editor}
      options={{ placement: "bottom", offset: 8 }}
      shouldShow={({ state, from, to }) => {
        const { empty } = state.selection;
        const hasText = state.doc.textBetween(from, to).trim().length > 0;
        return !empty && hasText && isTextSelection(state.selection);
      }}
      className="flex items-center gap-0.5 rounded-md border border-slate-200 bg-white p-1 shadow-md"
    >
      {isEditable && (
        <>
          <FormatButton
            label="Negrita"
            isActive={isBold}
            onClick={() => editor.chain().focus().toggleBold().run()}
          >
            <Bold className="h-4 w-4" />
          </FormatButton>
          <FormatButton
            label="Itálica"
            isActive={isItalic}
            onClick={() => editor.chain().focus().toggleItalic().run()}
          >
            <Italic className="h-4 w-4" />
          </FormatButton>
          <FormatButton
            label="Subrayado"
            isActive={isUnderline}
            onClick={() => editor.chain().focus().toggleUnderline().run()}
          >
            <Underline className="h-4 w-4" />
          </FormatButton>
          <span className="mx-0.5 h-5 w-px bg-slate-200" aria-hidden="true" />
        </>
      )}
      <FormatButton label="Copiar" onClick={handleCopySelection}>
        {copied ? (
          <Check className="h-4 w-4 text-emerald-600" />
        ) : (
          <Copy className="h-4 w-4" />
        )}
      </FormatButton>
    </BubbleMenu>
  );
};

export default SelectionBubbleMenu;
