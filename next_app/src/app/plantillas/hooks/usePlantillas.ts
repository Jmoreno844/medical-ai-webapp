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

    const openEditModal = (plantilla: Plantilla) => {
        setCurrentPlantilla(plantilla);
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
    };

    const createPlantilla = async (newPlantilla: NewPlantilla) => {
        try {
            await axiosInstance.post("/api/plantillas", newPlantilla);
            await fetchPlantillas();
            closeModals();
            return true;
        } catch (err) {
            console.error("Error creating plantilla:", err);
            return false;
        }
    };

    const updatePlantilla = async (
        id: number,
        updatedData: Partial<NewPlantilla>
    ) => {
        try {
            await axiosInstance.put(`/api/plantillas/${id}`, updatedData);
            await fetchPlantillas();
            closeModals();
            return true;
        } catch (err) {
            console.error("Error updating plantilla:", err);
            return false;
        }
    };

    const deletePlantilla = async (id: number) => {
        try {
            await axiosInstance.delete(`/api/plantillas/${id}`);
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
        openCreateModal,
        openEditModal,
        openDeleteModal,
        closeModals,
        createPlantilla,
        updatePlantilla,
        deletePlantilla,
    };
}
