import React, { useEffect, useMemo, useRef, useState } from "react";
import { debounce } from "lodash";
import { PatientInfoProps } from "../utils/EncuentroHeaderInterface";
import { DateTimePicker } from "@/commons/components/DateTimePicker";
import { Button } from "@/commons/components/ui/button";
import { Patient, usePatients } from "../hooks/usePatients";

const DEFAULT_ENCOUNTER_NAME = "Encuentro Nuevo";
const NEW_ENCOUNTER_LABEL = "Nuevo encuentro";
const TITLE_WIDTH = "8.9rem";

const getEditableEncounterName = (encounterName: string): string => {
  return encounterName === DEFAULT_ENCOUNTER_NAME ? "" : encounterName;
};

export interface ExtendedPatientInfoProps extends PatientInfoProps {
  isPatientConnected?: boolean;
  onOpenPatientModal?: () => void;
  onDelete?: () => void;
  onUpdateDate?: (date: Date) => void;
  onUpdateEncounterName?: (name: string) => Promise<boolean>;
  onSelectPatient?: (patientId: number, patientName: string) => Promise<void>;
  onCreateAndLinkPatient?: (patientName: string) => Promise<void>;
  originalDateString?: string | null;
  isDateUpdating?: boolean;
}

const PatientRow: React.FC<{
  patient: Patient;
  onSelect: (patient: Patient) => void;
}> = ({ patient, onSelect }) => (
  <button
    type="button"
    className="w-full px-3 py-2 text-left hover:bg-purple-50 focus:bg-purple-50 focus:outline-none"
    onMouseDown={(event) => event.preventDefault()}
    onClick={() => onSelect(patient)}
  >
    <span className="block text-sm font-medium text-slate-900">
      {patient.name}
    </span>
    {patient.summary && (
      <span className="block truncate text-xs text-slate-500">
        {patient.summary}
      </span>
    )}
  </button>
);

const PatientInfo: React.FC<ExtendedPatientInfoProps> = ({
  encounterName,
  encounterDate,
  isPatientConnected = false,
  onOpenPatientModal,
  onDelete,
  onUpdateDate,
  onUpdateEncounterName,
  onSelectPatient,
  onCreateAndLinkPatient,
  originalDateString,
  isDateUpdating = false,
}) => {
  const [datePickerValue, setDatePickerValue] = useState<Date | undefined>(
    originalDateString ? new Date(originalDateString) : undefined,
  );
  const [isDatePickerOpen, setIsDatePickerOpen] = useState(false);
  const [draftName, setDraftName] = useState(
    getEditableEncounterName(encounterName),
  );
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [suggestedPatients, setSuggestedPatients] = useState<Patient[]>([]);
  const [allPatients, setAllPatients] = useState<Patient[]>([]);
  const dropdownRef = useRef<HTMLDivElement | null>(null);
  const { searchPatients, isLoading } = usePatients();

  useEffect(() => {
    if (originalDateString) {
      const newDate = new Date(originalDateString);
      if (!isNaN(newDate.getTime())) {
        setDatePickerValue(newDate);
      }
    } else {
      setDatePickerValue(undefined);
    }
  }, [originalDateString]);

  useEffect(() => {
    setDraftName(getEditableEncounterName(encounterName));
  }, [encounterName]);

  const debouncedUpdateDate = useMemo(
    () =>
      debounce((date: Date) => {
        if (onUpdateDate) {
          onUpdateDate(date);
        }
      }, 800),
    [onUpdateDate],
  );

  const debouncedSaveEncounterName = useMemo(
    () =>
      debounce((name: string) => {
        onUpdateEncounterName?.(name);
      }, 700),
    [onUpdateEncounterName],
  );

  useEffect(() => {
    return () => {
      debouncedUpdateDate.cancel();
      debouncedSaveEncounterName.cancel();
    };
  }, [debouncedSaveEncounterName, debouncedUpdateDate]);

  useEffect(() => {
    if (isPatientConnected || !isDropdownOpen) {
      return;
    }

    let isActive = true;
    const query = draftName.trim();
    const timeoutId = window.setTimeout(async () => {
      const [allResults, suggestedResults] = await Promise.all([
        searchPatients(""),
        query.length >= 3 ? searchPatients(query) : Promise.resolve([]),
      ]);
      if (!isActive) {
        return;
      }
      setAllPatients(allResults);
      setSuggestedPatients(suggestedResults);
    }, 250);

    return () => {
      isActive = false;
      window.clearTimeout(timeoutId);
    };
  }, [draftName, isDropdownOpen, isPatientConnected, searchPatients]);

  useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  const handleDateChange = (date: Date) => {
    setDatePickerValue(date);
    debouncedUpdateDate(date);
  };

  const saveEncounterNameNow = () => {
    debouncedSaveEncounterName.cancel();
    onUpdateEncounterName?.(draftName);
  };

  const handleTitleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const nextName = event.target.value;
    setDraftName(nextName);
    setIsDropdownOpen(true);
    debouncedSaveEncounterName(nextName);
  };

  const handleSelectPatient = async (patient: Patient) => {
    setIsDropdownOpen(false);
    debouncedSaveEncounterName.cancel();
    setDraftName(patient.name);
    await onSelectPatient?.(patient.id, patient.name);
  };

  const handleCreatePatient = async () => {
    const name = draftName.trim();
    if (!name) {
      return;
    }
    setIsDropdownOpen(false);
    debouncedSaveEncounterName.cancel();
    await onCreateAndLinkPatient?.(name);
  };

  const linkedTitle =
    encounterName === DEFAULT_ENCOUNTER_NAME
      ? NEW_ENCOUNTER_LABEL
      : encounterName;

  const renderEditableTitle = () => (
    <div
      ref={dropdownRef}
      className="relative inline-grid max-w-[72vw]"
      style={{ width: TITLE_WIDTH }}
    >
      <input
        type="text"
        value={draftName}
        onChange={handleTitleChange}
        onFocus={() => setIsDropdownOpen(true)}
        onBlur={saveEncounterNameNow}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.currentTarget.blur();
          }
          if (event.key === "Escape") {
            setIsDropdownOpen(false);
          }
        }}
        className="col-start-1 row-start-1 w-full min-w-0 truncate rounded-md border border-transparent bg-transparent px-1 py-0.5 text-base font-medium text-slate-950 outline-none hover:border-slate-200 focus:border-purple-300 focus:bg-white focus:ring-2 focus:ring-purple-100"
        placeholder={NEW_ENCOUNTER_LABEL}
        data-testid="encounter-title-input"
      />

      {isDropdownOpen && (
        <div className="absolute left-0 top-full z-50 mt-1 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-md border border-slate-200 bg-white shadow-lg">
          {draftName.trim() && (
            <button
              type="button"
              className="w-full border-b border-slate-100 px-3 py-2 text-left text-sm font-medium text-purple-700 hover:bg-purple-50 focus:bg-purple-50 focus:outline-none"
              onMouseDown={(event) => event.preventDefault()}
              onClick={handleCreatePatient}
            >
              Crear paciente "{draftName.trim()}"
            </button>
          )}

          <div className="max-h-56 overflow-y-auto py-1">
            {suggestedPatients.length > 0 && (
              <div>
                <div className="px-3 py-1 text-xs font-semibold uppercase text-slate-500">
                  Pacientes sugeridos
                </div>
                {suggestedPatients.map((patient) => (
                  <PatientRow
                    key={`suggested-${patient.id}`}
                    patient={patient}
                    onSelect={handleSelectPatient}
                  />
                ))}
              </div>
            )}

            <div>
              <div className="px-3 py-1 text-xs font-semibold uppercase text-slate-500">
                Todos los pacientes
              </div>
              {allPatients.length > 0 ? (
                allPatients.map((patient) => (
                  <PatientRow
                    key={`all-${patient.id}`}
                    patient={patient}
                    onSelect={handleSelectPatient}
                  />
                ))
              ) : (
                <div className="px-3 py-2 text-sm text-slate-500">
                  {isLoading ? "Buscando..." : "No hay pacientes"}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );

  const renderLinkedTitle = () => (
    <Button
      type="button"
      variant="ghost"
      className="h-auto max-w-[72vw] justify-start px-1 py-0.5 text-base font-medium text-slate-950 hover:bg-slate-100"
      onClick={onOpenPatientModal}
      data-testid="linked-patient-title-button"
    >
      <span className="truncate">{linkedTitle}</span>
    </Button>
  );

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-2">
        {isPatientConnected ? renderLinkedTitle() : renderEditableTitle()}

        {onDelete && (
          <button
            onClick={onDelete}
            className="p-1 rounded-full hover:bg-gray-200 transition-colors"
            aria-label="Eliminar encuentro"
            title="Eliminar encuentro"
            data-testid="delete-encounter-button"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
            </svg>
          </button>
        )}
      </div>

      <div className="mt-2">
        {onUpdateDate ? (
          <div className="flex w-fit shrink-0 items-center rounded-lg border-2 border-gray-400">
            <DateTimePicker
              value={datePickerValue}
              onChange={handleDateChange}
              isOpen={isDatePickerOpen}
              onOpenChange={setIsDatePickerOpen}
            />
            {isDateUpdating && (
              <div className="ml-2 inline-block animate-spin rounded-full h-3 w-3 border-t-2 border-b-2 border-purple-500" />
            )}
          </div>
        ) : (
          <div className="flex items-center text-sm text-black">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4 mr-1"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
            <span>{encounterDate}</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default PatientInfo;
