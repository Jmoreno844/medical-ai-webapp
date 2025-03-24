import { useState, useEffect, useCallback } from "react";
import axiosInstance from "@/utils/axiosInstance";

export interface Plantilla {
    id: number;
    nombre: string;
    tipo_documento: string;
    veces_usada: number;
    ultimo_uso: string | null;
    es_base: boolean;
}

export interface NewPlantilla {
    nombre: string;
    tipo_documento: string;
    contenido?: string;
    contenido_base?: boolean;
    id_plantilla_base?: number | null;
}

export interface PlantillaDetalle {
    id: number;
    nombre: string;
    tipo_documento: string;
    contenido: string | null;
    contenido_base: boolean;
    id_plantilla_base: number | null;
}

export function usePlantillas() {
    const [plantillas, setPlantillas] = useState<Plantilla[]>([]);
    const [filteredPlantillas, setFilteredPlantillas] = useState<Plantilla[]>(
        []
    );
    const [searchQuery, setSearchQuery] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Modal states
    const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
    const [isEditModalOpen, setIsEditModalOpen] = useState(false);
    const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
    const [currentPlantilla, setCurrentPlantilla] = useState<Plantilla | null>(
        null
    );

    // Plantilla details states
    const [currentPlantillaDetails, setCurrentPlantillaDetails] =
        useState<PlantillaDetalle | null>(null);
    const [loadingPlantillaDetails, setLoadingPlantillaDetails] =
        useState(false);
    const [plantillaDetailsError, setPlantillaDetailsError] = useState<
        string | null
    >(null);

    const fetchPlantillas = useCallback(async () => {
        setLoading(true);
        try {
            const response = await axiosInstance.get("/api/plantillas_short");
            setPlantillas(response.data);
            setFilteredPlantillas(response.data);
            setError(null);
        } catch (err) {
            setError("Error al cargar las plantillas");
            console.error(err);
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
                plantilla.nombre
                    .toLowerCase()
                    .includes(searchQuery.toLowerCase())
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

    const fetchPlantillaDetails = useCallback(async (id_plantilla: number) => {
        setLoadingPlantillaDetails(true);
        setPlantillaDetailsError(null);

        try {
            const response = await axiosInstance.get(
                `/api/plantilla_doctor/${id_plantilla}`
            );
            setCurrentPlantillaDetails(response.data);
            return response.data;
        } catch (error) {
            console.error("Error fetching plantilla details:", error);
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
        // Fetch details when opening edit modal
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
            // This endpoint should accept all the fields we're sending
            await axiosInstance.post("/api/plantilla_doctor", newPlantilla);
            await fetchPlantillas();
            closeModals();
            return true;
        } catch (err) {
            console.error("Error creating plantilla:", err);
            return false;
        }
    };

    const updatePlantilla = async (
        id_plantilla: number,
        updatedData: Partial<NewPlantilla>
    ) => {
        try {
            await axiosInstance.patch(
                `/api/plantilla_doctor/${id_plantilla}`,
                updatedData
            );
            await fetchPlantillas();
            closeModals();
            return true;
        } catch (err) {
            console.error("Error updating plantilla:", err);
            return false;
        }
    };

    const deletePlantilla = async (id_plantilla: number) => {
        try {
            await axiosInstance.delete(`/api/plantillas/${id_plantilla}`);
            await fetchPlantillas();
            closeModals();
            return true;
        } catch (err) {
            console.error("Error deleting plantilla:", err);
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
