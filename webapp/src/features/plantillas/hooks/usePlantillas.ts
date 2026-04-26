import { useState, useEffect, useCallback } from "react";
import axiosInstance from "@/commons/utils/axiosInstance";
import { logger } from "@/lib/logger";

export interface Plantilla {
  id: number;
  name: string;
  document_kind: string;
  use_count: number;
  last_used_at: string | null;
  is_base: boolean;
}

export interface NewPlantilla {
  name: string;
  document_kind: string;
  content?: string;
  base_template_id?: number | null;
}

export interface PlantillaDetalle {
  id: number;
  name: string;
  document_kind: string;
  content: string | null;
  uses_base_content: boolean;
  base_template_id: number | null;
}

export function usePlantillas() {
  const [plantillas, setPlantillas] = useState<Plantilla[]>([]);
  const [filteredPlantillas, setFilteredPlantillas] = useState<Plantilla[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [currentPlantilla, setCurrentPlantilla] = useState<Plantilla | null>(
    null
  );

  const [currentPlantillaDetails, setCurrentPlantillaDetails] =
    useState<PlantillaDetalle | null>(null);
  const [loadingPlantillaDetails, setLoadingPlantillaDetails] = useState(false);
  const [plantillaDetailsError, setPlantillaDetailsError] = useState<
    string | null
  >(null);

  const fetchPlantillas = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axiosInstance.get("/api/v1/doctor-templates/short");
      setPlantillas(response.data);
      setFilteredPlantillas(response.data);
      setError(null);
    } catch (err) {
      setError("Error al cargar las plantillas");
      logger.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPlantillas();
  }, [fetchPlantillas]);

  useEffect(() => {
    if (searchQuery.trim() === "") {
      setFilteredPlantillas(plantillas);
    } else {
      const filtered = plantillas.filter((plantilla) =>
        plantilla.name.toLowerCase().includes(searchQuery.toLowerCase())
      );
      setFilteredPlantillas(filtered);
    }
  }, [searchQuery, plantillas]);

  const handleSearch = (query: string) => {
    setSearchQuery(query);
  };

  const openCreateModal = () => {
    setIsCreateModalOpen(true);
  };

  const fetchPlantillaDetails = useCallback(async (templateId: number) => {
    setLoadingPlantillaDetails(true);
    setPlantillaDetailsError(null);

    try {
      const response = await axiosInstance.get(
        `/api/v1/doctor-templates/${templateId}`
      );
      setCurrentPlantillaDetails(response.data);
      return response.data;
    } catch (error) {
      logger.error("Error fetching plantilla details:", error);
      setPlantillaDetailsError(
        "No se pudo cargar el contenido de la plantilla"
      );
      return null;
    } finally {
      setLoadingPlantillaDetails(false);
    }
  }, []);

  const openEditModal = async (plantilla: Plantilla) => {
    setCurrentPlantilla(plantilla);
    await fetchPlantillaDetails(plantilla.id);
    setIsEditModalOpen(true);
  };

  const openDeleteModal = (plantilla: Plantilla) => {
    setCurrentPlantilla(plantilla);
    setIsDeleteModalOpen(true);
  };

  const closeModals = () => {
    setIsCreateModalOpen(false);
    setIsEditModalOpen(false);
    setIsDeleteModalOpen(false);
    setCurrentPlantilla(null);
    setCurrentPlantillaDetails(null);
  };

  const createPlantilla = async (newPlantilla: NewPlantilla) => {
    try {
      const body: Record<string, unknown> = {
        name: newPlantilla.name,
        document_kind: newPlantilla.document_kind,
        content: newPlantilla.content ?? "",
      };
      if (newPlantilla.base_template_id != null) {
        body.base_template_id = newPlantilla.base_template_id;
      }
      await axiosInstance.post("/api/v1/doctor-templates", body);
      await fetchPlantillas();
      closeModals();
      return true;
    } catch (err) {
      logger.error("Error creating plantilla:", err);
      return false;
    }
  };

  const updatePlantilla = async (
    templateId: number,
    updatedData: Partial<NewPlantilla>
  ) => {
    try {
      await axiosInstance.patch(`/api/v1/doctor-templates/${templateId}`, {
        name: updatedData.name,
        document_kind: updatedData.document_kind,
        content: updatedData.content ?? "",
      });
      await fetchPlantillas();
      closeModals();
      return true;
    } catch (err) {
      logger.error("Error updating plantilla:", err);
      return false;
    }
  };

  const deletePlantilla = async (templateId: number) => {
    try {
      await axiosInstance.delete(`/api/v1/doctor-templates/${templateId}`);
      await fetchPlantillas();
      closeModals();
      return true;
    } catch (err) {
      logger.error("Error deleting plantilla:", err);
      return false;
    }
  };

  return {
    plantillas: filteredPlantillas,
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
    fetchPlantillaDetails,
  };
}
