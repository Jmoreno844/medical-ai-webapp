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
import {
  Plantilla,
  NewPlantilla,
  PlantillaDetalle,
} from "../hooks/usePlantillas";
import { Alert, AlertDescription } from "@/commons/components/ui/alert";

interface PlantillaModalProps {
  isOpen: boolean;
  onClose: () => void;
  modalType: "create" | "edit" | "delete";
  currentPlantilla: Plantilla | null;
  currentPlantillaDetails: PlantillaDetalle | null;
  loadingPlantillaDetails: boolean;
  plantillaDetailsError: string | null;
  onSubmit: (data: any, isBaseCopy?: boolean) => Promise<void>;
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
  isSubmitting,
}: PlantillaModalProps) {
  const [plantillaData, setPlantillaData] = useState<{
    nombre: string;
    tipo_documento: string;
    contenido: string;
  }>({
    nombre: "",
    tipo_documento: "documento",
    contenido: "",
  });

  const isBaseTemplate = currentPlantillaDetails?.contenido_base || false;

  // Update local state when plantilla details are fetched from the hook
  useEffect(() => {
    if (modalType === "edit" && currentPlantillaDetails) {
      let nombre = currentPlantillaDetails.nombre;

      // For base templates, add "(modificada)" to the name
      if (currentPlantillaDetails.contenido_base) {
        nombre = `${nombre} (modificada)`;
      }

      setPlantillaData({
        nombre,
        tipo_documento: currentPlantillaDetails.tipo_documento,
        contenido: currentPlantillaDetails.contenido || "",
      });
    } else if (modalType === "create") {
      setPlantillaData({
        nombre: "",
        tipo_documento: "documento",
        contenido: "",
      });
    } else if (currentPlantilla) {
      setPlantillaData({
        nombre: currentPlantilla.nombre,
        tipo_documento: currentPlantilla.tipo_documento,
        contenido: "",
      });
    }
  }, [modalType, currentPlantilla, currentPlantillaDetails]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSubmit(plantillaData, isBaseTemplate);
  };

  const getDialogDescription = () => {
    switch (modalType) {
      case "create":
        return "Crear una nueva plantilla para usar en documentos clínicos.";
      case "edit":
        return isBaseTemplate
          ? "Crear una copia modificada de la plantilla base."
          : "Editar los detalles y el contenido de la plantilla existente.";
      case "delete":
        return "Confirmar la eliminación de la plantilla seleccionada.";
    }
  };

  const renderModalContent = () => {
    switch (modalType) {
      case "create":
        return (
          <>
            <DialogHeader className="pb-2 border-b border-gray-100">
              <DialogTitle className="text-xl">
                Crear nueva plantilla
              </DialogTitle>
              <DialogDescription>{getDialogDescription()}</DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="flex flex-col h-full">
              <div className="space-y-4 py-4 flex-grow">
                <div>
                  <label
                    htmlFor="nombre"
                    className="block text-sm font-medium mb-1"
                  >
                    Nombre
                  </label>
                  <Input
                    id="nombre"
                    value={plantillaData.nombre}
                    onChange={(e) =>
                      setPlantillaData({
                        ...plantillaData,
                        nombre: e.target.value,
                      })
                    }
                    className="border-gray-200"
                    required
                  />
                </div>
                <div className="flex-grow">
                  <label
                    htmlFor="contenido"
                    className="block text-sm font-medium mb-1"
                  >
                    Contenido
                  </label>
                  <Textarea
                    id="contenido"
                    value={plantillaData.contenido}
                    onChange={(e) =>
                      setPlantillaData({
                        ...plantillaData,
                        contenido: e.target.value,
                      })
                    }
                    placeholder="Escribe el contenido de la plantilla aquí..."
                    className="min-h-[240px] resize-none border-gray-200"
                  />
                </div>
              </div>
              <DialogFooter className="flex items-center border-t border-gray-100 pt-4 gap-2">
                <div className="mr-auto">
                  <label htmlFor="tipo" className="text-sm font-medium mr-2">
                    Tipo:
                  </label>
                  <select
                    id="tipo"
                    value={plantillaData.tipo_documento}
                    onChange={(e) =>
                      setPlantillaData({
                        ...plantillaData,
                        tipo_documento: e.target.value,
                      })
                    }
                    className="border border-gray-200 rounded-md p-1 text-sm"
                    required
                  >
                    <option value="documento">Documento</option>
                    <option value="receta">Receta</option>
                    <option value="informe">Informe</option>
                  </select>
                </div>
                <Button
                  variant="outline"
                  type="button"
                  onClick={onClose}
                  className="border-gray-200"
                >
                  Cancelar
                </Button>
                <Button type="submit" disabled={isSubmitting} variant="primary">
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
                {isBaseTemplate ? "Copiar plantilla base" : "Editar plantilla"}
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
                      htmlFor="edit-nombre"
                      className="block text-sm font-medium mb-1"
                    >
                      Nombre
                    </label>
                    <Input
                      id="edit-nombre"
                      value={plantillaData.nombre}
                      onChange={(e) =>
                        setPlantillaData({
                          ...plantillaData,
                          nombre: e.target.value,
                        })
                      }
                      className="border-gray-200"
                      required
                    />
                  </div>
                  <div className="flex-grow">
                    <label
                      htmlFor="edit-contenido"
                      className="block text-sm font-medium mb-1"
                    >
                      Contenido
                    </label>
                    <Textarea
                      id="edit-contenido"
                      value={plantillaData.contenido}
                      onChange={(e) =>
                        setPlantillaData({
                          ...plantillaData,
                          contenido: e.target.value,
                        })
                      }
                      placeholder="Escribe el contenido de la plantilla aquí..."
                      className="min-h-[240px] resize-none border-gray-200"
                    />
                  </div>
                </div>
                <DialogFooter className="flex items-center border-t border-gray-100 pt-4 gap-2">
                  <div className="mr-auto">
                    <label
                      htmlFor="edit-tipo"
                      className="text-sm font-medium mr-2"
                    >
                      Tipo:
                    </label>
                    <select
                      id="edit-tipo"
                      value={plantillaData.tipo_documento}
                      onChange={(e) =>
                        setPlantillaData({
                          ...plantillaData,
                          tipo_documento: e.target.value,
                        })
                      }
                      className="border border-gray-200 rounded-md p-1 text-sm"
                      required
                    >
                      <option value="documento">Documento</option>
                      <option value="receta">Receta</option>
                      <option value="informe">Informe</option>
                    </select>
                  </div>
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
                    variant={isBaseTemplate ? "secondary" : "primary"}
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
                ¿Estás seguro de que quieres eliminar la plantilla "
                {currentPlantilla?.nombre}"?
              </p>
              <p className="text-sm text-gray-500 mt-2">
                Esta acción no se puede deshacer.
              </p>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={onClose}
                className="border-gray-200"
              >
                Cancelar
              </Button>
              <Button
                variant="destructive"
                onClick={handleSubmit}
                disabled={isSubmitting}
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
