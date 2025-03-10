import { useState, useEffect, useCallback } from "react";
import axiosInstance from "@/utils/axiosInstance";

// Define the Encuentro interface if it's not imported
export interface Encuentro {
    id: number;
    nombre_encuentro: string;
    fecha: string;
    id_paciente?: number;
    nombre_paciente?: string;
    paciente_conectado?: boolean;
    // Add other fields as needed
}

/**
 * Custom hook to fetch encounter details by ID
 * @param id - The ID of the encounter to fetch
 * @returns Object containing encounter data, loading state, and error information
 */
export const useEncuentroDetail = (id: number) => {
    const [encuentro, setEncuentro] = useState<Encuentro | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);

    const fetchData = useCallback(async () => {
        if (!id) {
            setError("ID no válido");
            setLoading(false);
            return;
        }

        setLoading(true);
        setError(null);
        console.log(`Fetching encounter data for ID: ${id}`);

        try {
            const response = await axiosInstance.get(`/api/encuentros/${id}`);
            console.log("Encounter data received:", response.data);
            setEncuentro(response.data);
        } catch (err: any) {
            const errorMsg =
                err.response?.data?.message ||
                err.message ||
                "Error desconocido";
            setError(errorMsg);
            console.error("Error fetching encounter:", errorMsg, err);
        } finally {
            setLoading(false);
        }
    }, [id]);

    // Initial data fetch
    useEffect(() => {
        fetchData();
    }, [fetchData]);

    // Return the refetch function along with data
    return {
        encuentro,
        loading,
        error,
        refetch: fetchData,
    };
};
