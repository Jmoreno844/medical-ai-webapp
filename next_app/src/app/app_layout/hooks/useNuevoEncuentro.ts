import { useState } from "react";
import { useRouter } from "next/navigation";
import axiosInstance from "@/utils/axiosInstance";
import { AxiosError } from "axios";

/**
 * Hook to handle the creation of a new medical encounter
 * @returns Object with loading state, error state, and function to create a new encounter
 */
export const useNuevoEncuentro = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const router = useRouter();

  /**
   * Creates a new encounter by calling the API and navigates to the new encounter page
   */
  const crearNuevoEncuentro = async () => {
    // Reset error state at the beginning of the operation
    setError(null);

    try {
      setLoading(true);
      console.log("Creating new encounter: Initiating API call");

      const response = await axiosInstance.post("/api/encuentros");
      const data = response.data;

      console.log(`New encounter created successfully with ID: ${data.id}`);

      // Navigate to the new encounter page
      console.log(`Navigating to encounter: /encuentro/${data.id}`);
      router.push(`/encuentro/${data.id}`);
    } catch (error) {
      // Handle different types of errors
      if (error instanceof AxiosError) {
        console.error(
          `API Error (${error.response?.status}): ${error.message}`
        );
        setError(
          new Error(error.response?.data?.message || `Error: ${error.message}`)
        );
      } else if (error instanceof TypeError) {
        // Network errors, like CORS or offline issues
        console.error(`Network Error: ${error.message}`);
        setError(
          new Error(
            "Error de red. Por favor, verifica tu conexión e inténtalo de nuevo."
          )
        );
      } else {
        console.error("Unexpected error creating encounter:", error);
        setError(
          error instanceof Error ? error : new Error("Error desconocido")
        );
      }
    } finally {
      setLoading(false);
      console.log("Encounter creation process completed");
    }
  };

  return {
    loading,
    error,
    crearNuevoEncuentro,
  };
};
