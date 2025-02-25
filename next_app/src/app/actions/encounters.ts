"use server";

interface CreateEncounterResponse {
  id: string;
  error?: string;
}

export const createEncounter = async (): Promise<CreateEncounterResponse> => {
  try {
    // TODO: Replace with your actual database call
    // Temporary mockup of creating an encounter
    const mockId = `enc_${Date.now()}`;

    return {
      id: mockId,
    };
  } catch (error) {
    return {
      id: "",
      error:
        error instanceof Error ? error.message : "Error creating encounter",
    };
  }
};
