import React, { useMemo, useState, useRef } from "react";
import {
  DocumentoOut,
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

interface TabBarProps {
  documents: DocumentoOut[];
  activeDocumentId: number | null;
  onSelectDocument: (documentId: number) => void;
  onGenerateDocumentation?: () => void;
  onDeleteDocument?: (documentId: number) => Promise<boolean>;
}

const TabBar: React.FC<TabBarProps> = ({
  documents,
  activeDocumentId,
  onSelectDocument,
  onGenerateDocumentation,
  onDeleteDocument,
}) => {
  // State for the delete confirmation dialog
  const [documentToDelete, setDocumentToDelete] = useState<DocumentoOut | null>(
    null
  );
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Ref for the DropdownMenu trigger and right-clicked document
  const dropdownTriggerRef = useRef<HTMLButtonElement>(null);
  const [activeDropdownDoc, setActiveDropdownDoc] =
    useState<DocumentoOut | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  // Sort documents with a stable sort order that won't change between renders
  const sortedDocuments = useMemo(() => {
    // Create a new array to avoid mutating the original
    return [...documents].sort((a, b) => {
      // Primary sort by creation date
      const dateA = new Date(a.fecha_creacion).getTime();
      const dateB = new Date(b.fecha_creacion).getTime();

      // If dates are different, sort by date
      if (dateA !== dateB) {
        return dateA - dateB;
      }

      // If dates are the same, use ID as a tiebreaker for stable ordering
      return a.id - b.id;
    });
  }, [documents]);

  // Check if a document can show context menu (all EXCEPT "contexto" and "transcripcion")
  const canShowContextMenu = (doc: DocumentoOut): boolean => {
    const tipo = doc.tipo.toLowerCase();
    return tipo !== "contexto" && tipo !== "transcripcion";
  };

  // Handler for right-click on tabs
  const handleContextMenu = (e: React.MouseEvent, doc: DocumentoOut) => {
    // Only show context menu for documents that are not contexto or transcripcion
    if (canShowContextMenu(doc)) {
      e.preventDefault(); // Prevent the browser's default context menu
      setActiveDropdownDoc(doc);
      setDropdownOpen(true);

      // Position the menu at the cursor position
      if (dropdownTriggerRef.current) {
        const clickX = e.clientX;
        const clickY = e.clientY;
        dropdownTriggerRef.current.style.position = "absolute";
        dropdownTriggerRef.current.style.left = `${clickX}px`;
        dropdownTriggerRef.current.style.top = `${clickY}px`;
        dropdownTriggerRef.current.click(); // Programmatically open the dropdown
      }
    }
  };

  // Handle document deletion
  const handleDeleteDocument = async () => {
    if (!documentToDelete || !onDeleteDocument) return;

    setIsDeleting(true);
    setDeleteError(null);

    try {
      const success = await onDeleteDocument(documentToDelete.id);
      if (!success) {
        setDeleteError("Error al eliminar el documento");
      } else {
        // Close the dialog after successful deletion
        setDocumentToDelete(null);
      }
    } catch (error) {
      console.error("Error deleting document:", error);
      setDeleteError("Error al eliminar el documento");
    } finally {
      setIsDeleting(false);
    }
  };

  if (!sortedDocuments.length) {
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
          {sortedDocuments.map((doc) => (
            <button
              key={doc.id}
              onClick={() => onSelectDocument(doc.id)}
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

          {/* Add document generation button right after the tabs */}
          {onGenerateDocumentation && (
            <button
              onClick={onGenerateDocumentation}
              className="p-2 text-blue-600 hover:bg-blue-100 rounded-full transition-colors self-center mx-2"
              title="Generar documentación"
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
          )}
        </div>

        {/* Display the document title in the tab bar */}
        {activeDocumentId && (
          <div className="px-4 text-sm font-medium text-gray-600">
            {getDocumentTitle(
              documents.find((doc) => doc.id === activeDocumentId)
            )}
          </div>
        )}
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
              <span>Borrar documento</span>
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

          <div className="py-4">
            <p>¿Estás seguro de que deseas eliminar este documento?</p>
            <p className="font-medium mt-2">
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
            >
              {isDeleting ? "Eliminando..." : "Eliminar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

// Helper function to get document title for display in the tab bar
function getDocumentTitle(doc?: DocumentoOut): string {
  if (!doc) return "";

  const docType = DOCUMENT_TYPE_LABELS_LONG[doc.tipo.toLowerCase()] || doc.tipo;
  const date = new Date(doc.fecha_creacion).toLocaleDateString("es-ES", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return `${docType} - ${date}`;
}

// Helper function to generate readable tab labels (kept for backward compatibility)
function getTabLabel(doc: DocumentoOut): string {
  return DOCUMENT_TYPE_LABELS[doc.tipo.toLowerCase()] || doc.tipo;
}

export default TabBar;
