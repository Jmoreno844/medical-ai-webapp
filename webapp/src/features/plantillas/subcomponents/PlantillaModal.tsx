import React, { useState, useEffect } from "react";
import { Button } from "@/commons/components/ui/button";
import { Input } from "@/commons/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/commons/components/ui/dialog";
import { Textarea } from "@/commons/components/ui/textarea";
import { Loader2, AlertTriangle } from "lucide-react";
import { Plantilla, PlantillaDetalle, NewPlantilla } from "../hooks/usePlantillas";
import { Alert, AlertDescription } from "@/commons/components/ui/alert";

const DOCUMENT_KIND_LABELS: Record<string, string> = {
  note: "Nota",
  document: "Documento",
  other: "Otros",
};

interface PlantillaModalProps {
  isOpen: boolean;
  onClose: () => void;
  modalType: "create" | "edit" | "delete";
  currentPlantilla: Plantilla | null;
  currentPlantillaDetails: PlantillaDetalle | null;
  loadingPlantillaDetails: boolean;
  plantillaDetailsError: string | null;
  onSubmit?: (data: NewPlantilla, isBaseCopy?: boolean) => Promise<void>;
  onDeleteConfirm?: () => Promise<void>;
  isSubmitting: boolean;
}

export function PlantillaModal({
  isOpen,
  onClose,
  modalType,
  currentPlantilla,
  currentPlantillaDetails,
  loadingPlantillaDetails,
  plantillaDetailsError,
  onSubmit,
  onDeleteConfirm,
  isSubmitting,
}: PlantillaModalProps) {
  const [plantillaData, setPlantillaData] = useState<NewPlantilla>({
    name: "",
    document_kind: "document",
    content: "",
  });

  const isBaseTemplate = currentPlantillaDetails?.uses_base_content || false;

  useEffect(() => {
    if (modalType === "edit" && currentPlantillaDetails) {
      let name = currentPlantillaDetails.name;

      if (currentPlantillaDetails.uses_base_content) {
        name = `${name} (modificada)`;
      }

      setPlantillaData({
        name,
        document_kind: currentPlantillaDetails.document_kind,
        content: currentPlantillaDetails.content || "",
      });
    } else if (modalType === "create") {
      setPlantillaData({
        name: "",
        document_kind: "document",
        content: "",
      });
    } else if (currentPlantilla) {
      setPlantillaData({
        name: currentPlantilla.name,
        document_kind: currentPlantilla.document_kind,
        content: "",
      });
    }
  }, [modalType, currentPlantilla, currentPlantillaDetails]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!onSubmit) return;
    await onSubmit(plantillaData, isBaseTemplate);
  };

  const getDialogDescription = () => {
    switch (modalType) {
      case "create":
        return "Cree una nueva plantilla para usar en documentos clínicos.";
      case "edit":
        return isBaseTemplate
          ? "Se creará una copia modificada de la plantilla base."
          : "Edite los datos y el contenido de la plantilla existente.";
      case "delete":
        return "Confirme la eliminación de la plantilla seleccionada.";
    }
  };

  const kindSelect = (idPrefix: string) => (
    <div className="mr-auto">
      <label htmlFor={`${idPrefix}-kind`} className="text-sm font-medium mr-2">
        Tipo:
      </label>
      <select
        id={`${idPrefix}-kind`}
        value={plantillaData.document_kind}
        onChange={(e) =>
          setPlantillaData({
            ...plantillaData,
            document_kind: e.target.value,
          })
        }
        className="border border-gray-200 rounded-md p-1 text-sm"
        required
      >
        {Object.entries(DOCUMENT_KIND_LABELS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
    </div>
  );

  const renderModalContent = () => {
    switch (modalType) {
      case "create":
        return (
          <>
            <DialogHeader className="pb-2 border-b border-gray-100">
              <DialogTitle className="text-xl">Nueva plantilla</DialogTitle>
              <DialogDescription>{getDialogDescription()}</DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="flex flex-col h-full">
              <div className="space-y-4 py-4 flex-grow">
                <div>
                  <label
                    htmlFor="template-name"
                    className="block text-sm font-medium mb-1"
                  >
                    Nombre
                  </label>
                  <Input
                    id="template-name"
                    value={plantillaData.name}
                    onChange={(e) =>
                      setPlantillaData({
                        ...plantillaData,
                        name: e.target.value,
                      })
                    }
                    className="border-gray-200"
                    required
                  />
                </div>
                <div className="flex-grow">
                  <label
                    htmlFor="template-content"
                    className="block text-sm font-medium mb-1"
                  >
                    Contenido
                  </label>
                  <Textarea
                    id="template-content"
                    value={plantillaData.content || ""}
                    onChange={(e) =>
                      setPlantillaData({
                        ...plantillaData,
                        content: e.target.value,
                      })
                    }
                    placeholder="Escriba aquí el contenido de la plantilla…"
                    className="min-h-[240px] resize-none border-gray-200"
                  />
                </div>
              </div>
              <DialogFooter className="flex items-center border-t border-gray-100 pt-4 gap-2">
                {kindSelect("create")}
                <Button
                  variant="outline"
                  type="button"
                  onClick={onClose}
                  className="border-gray-200"
                >
                  Cancelar
                </Button>
                <Button
                  type="submit"
                  disabled={isSubmitting}
                  variant="default"
                  className="bg-purple-500 hover:bg-purple-600"
                >
                  {isSubmitting && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Crear
                </Button>
              </DialogFooter>
            </form>
          </>
        );
      case "edit":
        return (
          <>
            <DialogHeader className="pb-2 border-b border-gray-100">
              <DialogTitle className="text-xl">
                {isBaseTemplate
                  ? "Copiar plantilla base"
                  : "Editar plantilla"}
              </DialogTitle>
              <DialogDescription>{getDialogDescription()}</DialogDescription>
            </DialogHeader>
            {loadingPlantillaDetails ? (
              <div className="flex justify-center items-center py-8">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            ) : plantillaDetailsError ? (
              <div className="bg-red-50 p-4 rounded-md text-red-800">
                {plantillaDetailsError}
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="flex flex-col h-full">
                {isBaseTemplate && (
                  <Alert className="my-2 bg-amber-50 border-amber-200 text-amber-800">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertDescription>
                      Las plantillas base no se pueden modificar directamente.
                      Se creará una copia personalizada.
                    </AlertDescription>
                  </Alert>
                )}
                <div className="space-y-4 py-4 flex-grow">
                  <div>
                    <label
                      htmlFor="edit-name"
                      className="block text-sm font-medium mb-1"
                    >
                      Nombre
                    </label>
                    <Input
                      id="edit-name"
                      value={plantillaData.name}
                      onChange={(e) =>
                        setPlantillaData({
                          ...plantillaData,
                          name: e.target.value,
                        })
                      }
                      className="border-gray-200"
                      required
                    />
                  </div>
                  <div className="flex-grow">
                    <label
                      htmlFor="edit-content"
                      className="block text-sm font-medium mb-1"
                    >
                      Contenido
                    </label>
                    <Textarea
                      id="edit-content"
                      value={plantillaData.content || ""}
                      onChange={(e) =>
                        setPlantillaData({
                          ...plantillaData,
                          content: e.target.value,
                        })
                      }
                      placeholder="Escriba aquí el contenido de la plantilla…"
                      className="min-h-[240px] resize-none border-gray-200"
                    />
                  </div>
                </div>
                <DialogFooter className="flex items-center border-t border-gray-100 pt-4 gap-2">
                  {kindSelect("edit")}
                  <Button
                    variant="outline"
                    type="button"
                    onClick={onClose}
                    className="border-gray-300 hover:border-gray-500"
                  >
                    Cancelar
                  </Button>
                  <Button
                    type="submit"
                    disabled={isSubmitting}
                    variant={"destructive"}
                    className="bg-purple-500 hover:bg-purple-600"
                  >
                    {isSubmitting && (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    )}
                    {isBaseTemplate ? "Crear copia" : "Guardar cambios"}
                  </Button>
                </DialogFooter>
              </form>
            )}
          </>
        );
      case "delete":
        return (
          <>
            <DialogHeader>
              <DialogTitle>Eliminar plantilla</DialogTitle>
              <DialogDescription>{getDialogDescription()}</DialogDescription>
            </DialogHeader>
            <div className="py-4">
              <p>
                ¿Seguro que desea eliminar la plantilla «
                {currentPlantilla?.name}»?
              </p>
              <p className="text-sm text-gray-500 mt-2">
                Esta acción no se puede deshacer.
              </p>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={onClose}
                className="border-gray-300 hover:border-gray-500"
              >
                Cancelar
              </Button>
              <Button
                variant="destructive"
                onClick={() => void onDeleteConfirm?.()}
                disabled={isSubmitting}
                className="bg-red-600 hover:bg-red-700"
              >
                {isSubmitting && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Eliminar
              </Button>
            </DialogFooter>
          </>
        );
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className={`${
          modalType !== "delete" ? "max-w-3xl" : "max-w-md"
        } border-gray-200 shadow-lg`}
      >
        {renderModalContent()}
      </DialogContent>
    </Dialog>
  );
}
