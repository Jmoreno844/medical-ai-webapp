import React, { useState, useEffect } from "react";
import { PatientEditModalProps } from "./utils/EncuentroHeaderInterface";
import { usePatients, Patient } from "./hooks/usePatients";

/**
 * Component to render a single patient search result
 */
const PatientSearchResult: React.FC<{
  patient: Patient;
  onSelect: (id: number, name: string) => void;
}> = ({ patient, onSelect }) => (
  <li
    key={patient.id}
    className="p-2 hover:bg-gray-100 cursor-pointer"
    onClick={() => onSelect(patient.id, patient.nombre)}
    role="option"
  >
    <div>
      <span className="font-medium">{patient.nombre}</span>
      {patient.resumen && (
        <p className="text-xs text-gray-500 truncate mt-1">{patient.resumen}</p>
      )}
    </div>
  </li>
);

/**
 * Modal component for editing patient and encounter information
 *
 * This component has two modes:
 * 1. Patient connection mode - For searching existing patients or creating new ones
 * 2. Edit mode - For updating information when a patient is already connected
 *
 * @param props - Component props defined in PatientEditModalProps
 * @returns Modal dialog component
 */
const PatientEditModal: React.FC<PatientEditModalProps> = ({
  isOpen,
  onClose,
  onSelectPatient,
  onCreatePatient,
  isPatientConnected = false,
  currentEncounterName = "",
  currentPatientId = 0,
  currentPatientName = "",
  onUpdatePatientAndEncounter = () => {},
}) => {
  // ========== STATE MANAGEMENT ==========
  // For patient selection/creation mode
  const [patientName, setPatientName] = useState("");
  const [selectedPatientId, setSelectedPatientId] = useState<number | null>(
    null
  );
  const [searchResults, setSearchResults] = useState<Patient[]>([]);
  // Add a flag to prevent re-searching after selection
  const [justSelected, setJustSelected] = useState(false);
  // Track the selected patient's name to compare with input changes
  const [selectedPatientName, setSelectedPatientName] = useState<string>("");
  // Cache for previously found patients to enable automatic reselection
  const [foundPatientsCache, setFoundPatientsCache] = useState<
    Map<string, number>
  >(new Map());

  // For edit mode (when patient is already connected)
  const [connectedName, setConnectedName] = useState("");

  // Patient API hook
  const { createPatient, searchPatients, isLoading, error } = usePatients();

  // ========== EFFECTS ==========
  /**
   * Initialize state when modal opens based on mode
   */
  useEffect(() => {
    if (isOpen) {
      if (isPatientConnected) {
        // Use the current name for the single input in edit mode
        setConnectedName(currentPatientName || currentEncounterName);
      } else {
        // Reset search state in selection mode
        setPatientName("");
        setSelectedPatientId(null);
        setSearchResults([]);
        setJustSelected(false);
        setSelectedPatientName("");
        // Keep the cache to allow selecting previously found patients
      }
    }
  }, [isOpen, isPatientConnected, currentEncounterName, currentPatientName]);

  /**
   * Handle changes to patient name input
   * - Clear selection if text doesn't match selected patient
   * - Auto-select if the text exactly matches a known patient
   */
  useEffect(() => {
    // Skip if in connected mode or if search is already in progress
    if (isPatientConnected || justSelected) return;

    // If we had a patient selected, but the text no longer matches, clear the selection
    if (selectedPatientId !== null && patientName !== selectedPatientName) {
      setSelectedPatientId(null);
      setSelectedPatientName("");
    }

    // If text exactly matches a patient in our cache, auto-select that patient
    const cachedPatientId = foundPatientsCache.get(patientName.toLowerCase());
    if (cachedPatientId && !selectedPatientId) {
      setSelectedPatientId(cachedPatientId);
      setSelectedPatientName(patientName);
      setSearchResults([]);
    }
  }, [
    patientName,
    selectedPatientId,
    selectedPatientName,
    foundPatientsCache,
    isPatientConnected,
    justSelected,
  ]);

  /**
   * Debounced patient search
   */
  useEffect(() => {
    if (!isPatientConnected) {
      // Skip search if a patient was just selected
      if (justSelected) {
        setJustSelected(false);
        return;
      }

      const handler = setTimeout(() => {
        if (patientName.length > 2) {
          handleSearch(patientName);
        } else {
          setSearchResults([]);
        }
      }, 300);

      return () => {
        clearTimeout(handler);
      };
    }
  }, [patientName, isPatientConnected, justSelected]);

  // ========== EVENT HANDLERS ==========
  /**
   * Search for patients by name
   */
  const handleSearch = async (query: string) => {
    if (query.length > 2) {
      const results = await searchPatients(query);
      setSearchResults(results);

      // Update our cache of known patients
      const updatedCache = new Map(foundPatientsCache);
      results.forEach((patient) => {
        updatedCache.set(patient.nombre.toLowerCase(), patient.id);
      });
      setFoundPatientsCache(updatedCache);
    }
  };

  /**
   * Handle patient selection from search results
   */
  const handleSelectResult = (id: number, name: string) => {
    setSelectedPatientId(id);
    setPatientName(name);
    setSelectedPatientName(name); // Store the selected name for comparison
    setSearchResults([]);
    setJustSelected(true);

    // Add to our cache of known patients
    setFoundPatientsCache((prev) => new Map(prev).set(name.toLowerCase(), id));
  };

  /**
   * Handle selecting an existing patient
   */
  const handleSelectPatient = () => {
    if (selectedPatientId) {
      onSelectPatient(selectedPatientId, patientName);
      onClose();
    }
  };

  /**
   * Handle creating a new patient
   */
  const handleCreatePatient = async () => {
    if (patientName.trim()) {
      const newPatient = await createPatient(patientName.trim());

      if (newPatient) {
        console.log("Patient created successfully:", newPatient);
        onCreatePatient(newPatient.nombre);
        onSelectPatient(newPatient.id, newPatient.nombre);
        onClose();
      } else {
        console.error("Failed to create patient");
      }
    }
  };

  /**
   * Handle updating both patient and encounter names
   */
  const handleUpdateEncounter = () => {
    if (connectedName.trim()) {
      const patientIdToUse = currentPatientId !== null ? currentPatientId : 0;

      onUpdatePatientAndEncounter(
        patientIdToUse,
        connectedName.trim(),
        connectedName.trim()
      );
      onClose();
    }
  };

  /**
   * Handle input changes in the patient name field
   */
  const handlePatientNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setPatientName(newValue);
  };

  // Don't render if the modal is not open
  if (!isOpen) return null;

  // ========== RENDER ==========
  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      data-testid="patient-edit-modal"
    >
      <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
        {/* Modal header */}
        <h2 className="text-xl font-semibold mb-4">
          {isPatientConnected ? "Edit Patient Name" : "Link Patient"}
        </h2>

        {/* Modal content based on mode */}
        {isPatientConnected ? (
          // Edit mode (patient already connected)
          <div className="mb-4">
            <label
              htmlFor="connectedName"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Patient or Encounter Name
            </label>
            <input
              type="text"
              id="connectedName"
              value={connectedName}
              onChange={(e) => setConnectedName(e.target.value)}
              className="w-full p-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="Patient or Encounter Name"
              data-testid="connected-name-input"
            />
          </div>
        ) : (
          // Search/create mode (no patient connected)
          <div className="mb-4">
            <label
              htmlFor="patientName"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Patient Name
            </label>
            <input
              type="text"
              id="patientName"
              value={patientName}
              onChange={handlePatientNameChange}
              className="w-full p-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="Search existing patient or enter new"
              data-testid="patient-name-input"
            />
          </div>
        )}

        {/* Error display */}
        {error && (
          <div
            className="mb-4 p-2 bg-red-100 text-red-700 rounded border border-red-200"
            role="alert"
          >
            {error}
          </div>
        )}

        {/* Search loading indicator and results */}
        {!isPatientConnected && isLoading ? (
          <div className="mb-4 p-2 text-center">
            <div className="inline-block animate-spin rounded-full h-5 w-5 border-t-2 border-b-2 border-purple-500"></div>
            <span className="ml-2">Searching...</span>
          </div>
        ) : (
          !isPatientConnected &&
          searchResults.length > 0 &&
          !selectedPatientId && ( // Don't show results if a patient is already selected
            <div
              className="mb-4 max-h-40 overflow-y-auto border border-gray-200 rounded"
              role="listbox"
            >
              <ul>
                {searchResults.map((result) => (
                  <PatientSearchResult
                    key={result.id}
                    patient={result}
                    onSelect={handleSelectResult}
                  />
                ))}
              </ul>
            </div>
          )
        )}

        {/* Modal actions */}
        <div className="flex justify-end space-x-3 mt-6">
          <button
            className="px-4 py-2 bg-gray-200 text-gray-800 rounded hover:bg-gray-300"
            onClick={onClose}
          >
            Cancel
          </button>

          {isPatientConnected ? (
            // Button for updating existing encounter and patient
            <button
              className="px-4 py-2 bg-purple-500 text-white rounded hover:bg-purple-600 disabled:bg-purple-300"
              onClick={handleUpdateEncounter}
              disabled={!connectedName.trim() || isLoading}
              data-testid="update-button"
            >
              Update
            </button>
          ) : (
            // Buttons for selecting or creating new patient
            <>
              <button
                className="px-4 py-2 bg-purple-500 text-white rounded hover:bg-purple-600 disabled:bg-purple-300"
                onClick={handleSelectPatient}
                disabled={!selectedPatientId || isLoading}
                data-testid="select-patient-button"
              >
                Select Patient
              </button>
              <button
                className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-blue-300"
                onClick={handleCreatePatient}
                disabled={
                  !patientName.trim() || isLoading || selectedPatientId !== null
                }
                data-testid="create-patient-button"
              >
                {isLoading ? "Creating..." : "Create Patient"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default PatientEditModal;
