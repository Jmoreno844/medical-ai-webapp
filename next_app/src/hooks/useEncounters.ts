import { useState, useEffect } from "react";
import { getDoctorEncounters } from "@/services/encounterService";
import { Encounter } from "@/types/encounter";

export const useEncounters = () => {
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchEncounters = async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await getDoctorEncounters();
      setEncounters(data);
    } catch (err) {
      setError("Failed to load encounters");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (true) {
      fetchEncounters();
    }
  }, []);

  return {
    encounters,
    loading,
    error,
    refreshEncounters: () => fetchEncounters(),
  };
};
