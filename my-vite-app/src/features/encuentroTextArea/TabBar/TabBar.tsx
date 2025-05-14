import React, { useMemo, useState, useRef } from "react";
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

// Import context
import { useDocumentContext } from "@/contexts/DocumentContext";
import { useGenerationContext } from "@/contexts/GenerationContext";
import { useTranscriptionContext } from "@/contexts/TranscriptionContext"; // Updated import

const TabBar: React.FC = () => {
  // Get state from context
  const { documents, activeDocumentId, selectDocument, deleteDocument } =
    useDocumentContext();

  const { openGenerationModal } = useGenerationContext();
  const { hasBeenTranscribed } = useTranscriptionContext(); // Use hasBeenTranscribed directly

  // Local state for UI
  const [documentToDelete, setDocumentToDelete] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);
  const dropdownTriggerRef = useRef<HTMLButtonElement>(null);
  const [activeDropdownDoc, setActiveDropdownDoc] = useState(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  // Sort documents (same code as before)
  const sortedDocuments = useMemo(() => {
    return [...documents].sort((a, b) => {
      const dateA = new Date(a.fecha_creacion).getTime();
      const dateB = new Date(b.fecha_creacion).getTime();

      if (dateA !== dateB) {
        return dateA - dateB;
      }

      return a.id - b.id;
    });
  }, [documents]);

  // Check if a document can show context menu
  const canShowContextMenu = (doc) => {
    const tipo = doc.tipo.toLowerCase();
    return tipo !== "contexto" && tipo !== "transcripcion";
  };

  // Handle right-click on tabs
  const handleContextMenu = (e, doc) => {
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

  // Handle document deletion
  const handleDeleteDocument = async () => {
    if (!documentToDelete) return;

    setIsDeleting(true);
    setDeleteError(null);

    try {
      const success = await deleteDocument(documentToDelete.id);
      if (!success) {
        setDeleteError("Error deleting document");
      } else {
        setDocumentToDelete(null);
      }
    } catch (error) {
      console.error("Error deleting document:", error);
      setDeleteError("Error deleting document");
    } finally {
      setIsDeleting(false);
    }
  };

  if (!sortedDocuments.length) {
    return (
      <div className="bg-gray-100 p-2 text-sm text-gray-500 border-b">
        No documents available
      </div>
    );
  }

  return (
    <>
      <div className="flex justify-between items-center bg-gray-100 border-b">
        <div className="flex overflow-x-auto flex-grow">
          {sortedDocuments.map((doc) => (
            <button
              key={doc.id}
              onClick={() => selectDocument(doc.id)}
              onContextMenu={(e) => handleContextMenu(e, doc)}
              className={`px-4 py-2 min-w-[120px] text-sm font-medium whitespace-nowrap transition-colors
                ${
                  activeDocumentId === doc.id
                    ? "bg-white text-blue-600 border-t-2 border-blue-600"
                    : "text-gray-600 hover:bg-gray-200"
                }`}
              aria-label={`Select ${getTabLabel(doc)}`}
              data-document-type={doc.tipo}
            >
              {DOCUMENT_TYPE_LABELS[doc.tipo.toLowerCase()] || doc.tipo}
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
                ? "Generate documentation"
                : "Transcribe audio first to generate documentation"
            }
            aria-label="Generate documentation"
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
              <span>Delete Document</span>
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
            <DialogTitle>Delete document</DialogTitle>
          </DialogHeader>

          <div className="">
            <p>Are you sure you want to delete this document?</p>
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
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteDocument}
              disabled={isDeleting}
              className="bg-red-600 text-white hover:bg-red-700 border border-red-600 font-medium"
            >
              {isDeleting ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

// Helper functions (same as before)
function getDocumentTitle(doc) {
  if (!doc) return "";

  const docType = DOCUMENT_TYPE_LABELS_LONG[doc.tipo.toLowerCase()] || doc.tipo;
  const date = new Date(doc.fecha_creacion).toLocaleDateString("en-EN", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return `${docType} - ${date}`;
}

function getTabLabel(doc) {
  return DOCUMENT_TYPE_LABELS[doc.tipo.toLowerCase()] || doc.tipo;
}

export default TabBar;
