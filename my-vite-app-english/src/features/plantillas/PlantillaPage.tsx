import { useState } from "react";
import { usePlantillas, NewPlantilla } from "./hooks/usePlantillas";
import { Button } from "@/commons/components/ui/button";
import { Input } from "@/commons/components/ui/input";
import { Card, CardContent } from "@/commons/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/commons/components/ui/dropdown-menu";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import {
  Search,
  PlusCircle,
  MoreVertical,
  Edit,
  Trash2,
  Loader2,
} from "lucide-react";
import { PlantillaModal } from "./subcomponents/PlantillaModal";

export default function PlantillasPage() {
  const {
    plantillas,
    loading,
    error,
    searchQuery,
    handleSearch,
    isCreateModalOpen,
    isEditModalOpen,
    isDeleteModalOpen,
    currentPlantilla,
    currentPlantillaDetails,
    loadingPlantillaDetails,
    plantillaDetailsError,
    openCreateModal,
    openEditModal,
    openDeleteModal,
    closeModals,
    createPlantilla,
    updatePlantilla,
    deletePlantilla,
  } = usePlantillas();

  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleCreateSubmit = async (data: NewPlantilla) => {
    setIsSubmitting(true);
    await createPlantilla(data);
    setIsSubmitting(false);
  };

  const handleEditSubmit = async (
    data: Partial<NewPlantilla>,
    isBaseCopy: boolean = false
  ) => {
    if (!currentPlantilla) return;

    setIsSubmitting(true);

    if (isBaseCopy) {
      // Create a copy of the base template
      const newTemplateData: NewPlantilla = {
        nombre: data.nombre || "", // Ensure it's not undefined
        tipo_documento: data.tipo_documento || "documento", // Ensure it's not undefined
        contenido: data.contenido,
        contenido_base: false,
        id_plantilla_base: currentPlantilla.id,
      };

      await createPlantilla(newTemplateData);
    } else {
      // Normal update for non-base templates
      await updatePlantilla(currentPlantilla.id, data);
    }

    setIsSubmitting(false);
  };

  const handleDeleteConfirm = async () => {
    if (!currentPlantilla) return;
    setIsSubmitting(true); // Fixed missing opening parenthesis
    await deletePlantilla(currentPlantilla.id);
    setIsSubmitting(false);
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return "Never"; // Consider translating "Never" to "Nunca" if appropriate for context

    try {
      return format(new Date(dateString), "dd/MM/yyyy HH:mm", {
        locale: es,
      });
    } catch (e) {
      return "Error de formato de fecha";
    }
  };

  return (
    <div className="container mx-auto py-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Plantillas</h1>
        <Button
          onClick={openCreateModal}
          variant="outline"
          className="flex items-center gap-2 bg-purple-600 text-white font-medium 
          text-base hover:bg-purple-500 transition-colors hover:text-white"
        >
          <PlusCircle className="h-4 w-4" />
          Crear Plantilla
        </Button>
      </div>

      <div className="relative mb-6">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-500 h-4 w-4" />
        <Input
          className="pl-10"
          placeholder="Buscar plantillas por nombre..."
          value={searchQuery}
          onChange={(e) => handleSearch(e.target.value)}
        />
      </div>

      {loading ? (
        <div className="flex justify-center items-center h-40">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : error ? (
        <div className="bg-red-50 p-4 rounded-md text-red-800">{error}</div>
      ) : plantillas.length === 0 ? (
        <div className="bg-slate-50 p-8 text-center rounded-md">
          {searchQuery
            ? "No se encontraron plantillas con ese nombre."
            : "No hay plantillas disponibles."}
        </div>
      ) : (
        <div className="space-y-4">
          {plantillas.map((plantilla) => (
            <Card key={plantilla.id} className="overflow-hidden">
              <CardContent className="p-0">
                <div className="flex justify-between items-center p-4">
                  <div className="flex-1">
                    <h3 className="font-medium">{plantilla.nombre}</h3>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-2 text-sm text-gray-600">
                      <div>Veces usada: {plantilla.veces_usada}</div>
                      <div>Último uso: {formatDate(plantilla.ultimo_uso)}</div>
                      <div>Tipo: {plantilla.es_base ? "Base" : "Personalizada"}</div>
                    </div>
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon">
                        <MoreVertical className="h-5 w-5" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        onClick={() => openEditModal(plantilla)}
                        className="flex items-center gap-2 cursor-pointer"
                      >
                        <Edit className="h-4 w-4" />
                        Editar
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={() => openDeleteModal(plantilla)}
                        className="flex items-center gap-2 cursor-pointer text-red-600"
                      >
                        <Trash2 className="h-4 w-4" />
                        Eliminar
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Modal */}
      <PlantillaModal
        isOpen={isCreateModalOpen}
        onClose={closeModals}
        modalType="create"
        currentPlantilla={null}
        currentPlantillaDetails={null}
        loadingPlantillaDetails={false}
        plantillaDetailsError={null}
        onSubmit={handleCreateSubmit}
        isSubmitting={isSubmitting}
      />

      {/* Edit Modal */}
      <PlantillaModal
        isOpen={isEditModalOpen}
        onClose={closeModals}
        modalType="edit"
        currentPlantilla={currentPlantilla}
        currentPlantillaDetails={currentPlantillaDetails}
        loadingPlantillaDetails={loadingPlantillaDetails}
        plantillaDetailsError={plantillaDetailsError}
        onSubmit={handleEditSubmit}
        isSubmitting={isSubmitting}
      />

      {/* Delete Modal */}
      <PlantillaModal
        isOpen={isDeleteModalOpen}
        onClose={closeModals}
        modalType="delete"
        currentPlantilla={currentPlantilla}
        currentPlantillaDetails={null}
        loadingPlantillaDetails={false}
        plantillaDetailsError={null}
        onSubmit={handleDeleteConfirm}
        isSubmitting={isSubmitting}
      />
    </div>
  );
}
