import React, { useMemo, useRef, useState } from "react";
import {
  DOCUMENT_TYPE_LABELS,
  DOCUMENT_TYPE_LABELS_LONG,
} from "@/types/documento";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/commons/components/ui/dialog";
import { Button } from "@/commons/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/commons/components/ui/dropdown-menu";
import { Trash } from "lucide-react";

import { useDocumentContext } from "@/contexts/DocumentContext";
import { useGenerationContext } from "@/contexts/GenerationContext";
import { useTranscriptionContext } from "@/contexts/TranscriptionContext";
import { logger } from "@/lib/logger";
import { useWorkspaceStore } from "@/workspace/stores/workspaceStore";
import { WorkspaceDocument } from "@/workspace/types";

const TabBar: React.FC = () => {
  const { deleteDocument } = useDocumentContext();
  const documentOrder = useWorkspaceStore((state) => state.documentOrder);
  const documentsById = useWorkspaceStore((state) => state.documentsById);
  const activeDocumentId = useWorkspaceStore((state) => state.activeDocumentId);
  const setActiveDocument = useWorkspaceStore(
    (state) => state.setActiveDocument,
  );
  const documents = useMemo(
    () =>
      documentOrder
        .map((documentId) => documentsById[documentId])
        .filter(Boolean),
    [documentOrder, documentsById],
  );
  const { openGenerationModal } = useGenerationContext();
  const { hasBeenTranscribed } = useTranscriptionContext();

  const [documentToDelete, setDocumentToDelete] =
    useState<WorkspaceDocument | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const dropdownTriggerRef = useRef<HTMLButtonElement>(null);
  const [activeDropdownDoc, setActiveDropdownDoc] =
    useState<WorkspaceDocument | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const canShowContextMenu = (doc: WorkspaceDocument) => {
    const kind = doc.type.toLowerCase();
    return kind !== "context" && kind !== "transcription";
  };

  const handleContextMenu = (e: React.MouseEvent, doc: WorkspaceDocument) => {
    if (canShowContextMenu(doc)) {
      e.preventDefault();
      setActiveDropdownDoc(doc);
      setDropdownOpen(true);

      if (dropdownTriggerRef.current) {
        const clickX = e.clientX;
        const clickY = e.clientY;
        dropdownTriggerRef.current.style.position = "absolute";
        dropdownTriggerRef.current.style.left = `${clickX}px`;
        dropdownTriggerRef.current.style.top = `${clickY}px`;
        dropdownTriggerRef.current.click();
      }
    }
  };

  const handleDeleteDocument = async () => {
    if (!documentToDelete) return;

    setIsDeleting(true);
    setDeleteError(null);

    try {
      const success = await deleteDocument(Number(documentToDelete.id));
      if (!success) {
        setDeleteError("No se pudo eliminar el documento");
      } else {
        setDocumentToDelete(null);
      }
    } catch (error) {
      logger.error("Error deleting document:", error);
      setDeleteError("No se pudo eliminar el documento");
    } finally {
      setIsDeleting(false);
    }
  };

  if (!documents.length) {
    return (
      <div className="bg-gray-100 p-2 text-sm text-gray-500 border-b">
        No hay documentos disponibles
      </div>
    );
  }

  return (
    <>
      <div className="flex justify-between items-center bg-gray-100 border-b">
        <div className="flex overflow-x-auto flex-grow">
          {documents.map((doc) => (
            <button
              key={doc.id}
              onClick={() => setActiveDocument(doc.id)}
              onContextMenu={(e) => handleContextMenu(e, doc)}
              className={`px-4 py-2 min-w-[120px] text-sm font-medium whitespace-nowrap transition-colors
                ${
                  activeDocumentId === doc.id
                    ? "bg-white text-blue-600 border-t-2 border-blue-600"
                    : "text-gray-600 hover:bg-gray-200"
                }`}
              aria-label={`Seleccionar ${getTabLabel(doc)}`}
              data-document-type={doc.type}
            >
              {doc.title ||
                DOCUMENT_TYPE_LABELS[doc.type.toLowerCase()] ||
                doc.type}
            </button>
          ))}

          {/* Add document generation button */}
          <button
            onClick={openGenerationModal}
            disabled={!hasBeenTranscribed}
            className={`p-2 ${
              hasBeenTranscribed
                ? "text-blue-600 hover:bg-blue-100"
                : "text-gray-400 cursor-not-allowed"
            } rounded-full transition-colors self-center mx-2`}
            title={
              hasBeenTranscribed
                ? "Generar documentación"
                : "Transcriba el audio primero para generar documentación"
            }
            aria-label="Generar documentación"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Hidden dropdown trigger */}
      <DropdownMenu open={dropdownOpen} onOpenChange={setDropdownOpen}>
        <DropdownMenuTrigger asChild>
          <button
            ref={dropdownTriggerRef}
            className="sr-only"
            aria-hidden="true"
            tabIndex={-1}
          />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          {activeDropdownDoc && (
            <DropdownMenuItem
              className="text-red-500 cursor-pointer flex items-center"
              onClick={() => {
                setDocumentToDelete(activeDropdownDoc);
                setDropdownOpen(false);
              }}
            >
              <Trash className="mr-2 h-4 w-4" />
              <span>Eliminar documento</span>
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Delete confirmation dialog */}
      <Dialog
        open={!!documentToDelete}
        onOpenChange={(open) => !open && setDocumentToDelete(null)}
      >
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Eliminar documento</DialogTitle>
          </DialogHeader>

          <div className="">
            <p>¿Seguro que desea eliminar este documento?</p>
            <p className="font-medium mt-8 mb-4 text-center">
              {documentToDelete && getDocumentTitle(documentToDelete)}
            </p>

            {deleteError && (
              <div className="mt-4 p-3 text-sm font-medium text-red-500 bg-red-50 border border-red-100 rounded-md">
                {deleteError}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDocumentToDelete(null)}
              className="mr-2"
              disabled={isDeleting}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteDocument}
              disabled={isDeleting}
              className="bg-red-600 text-white hover:bg-red-700 border border-red-600 font-medium"
            >
              {isDeleting ? "Eliminando…" : "Eliminar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

// Helper functions (same as before)
function getDocumentTitle(doc: WorkspaceDocument | null) {
  if (!doc) return "";

  const docType =
    doc.title || DOCUMENT_TYPE_LABELS_LONG[doc.type.toLowerCase()] || doc.type;
  const date = new Date(doc.createdAt).toLocaleDateString("es-ES", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return `${docType} - ${date}`;
}

function getTabLabel(doc: WorkspaceDocument) {
  return doc.title || DOCUMENT_TYPE_LABELS[doc.type.toLowerCase()] || doc.type;
}

export default TabBar;
