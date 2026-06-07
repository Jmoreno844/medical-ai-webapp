import React, { useEffect, useState } from "react";
import { Trash2, Unlink } from "lucide-react";
import { PatientEditModalProps } from "./utils/EncuentroHeaderInterface";

const PatientEditModal: React.FC<PatientEditModalProps> = ({
  isOpen,
  onClose,
  currentPatientId = 0,
  currentPatientName = "",
  currentEncounterName = "",
  onUpdatePatient,
  onUnlinkEncounter,
  onDeletePatient,
  isUpdating = false,
}) => {
  const [patientName, setPatientName] = useState("");
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setPatientName(currentPatientName || currentEncounterName || "");
      setIsDeleteConfirmOpen(false);
    }
  }, [currentEncounterName, currentPatientName, isOpen]);

  if (!isOpen) {
    return null;
  }

  const isBusy = isSaving || isUpdating;
  const normalizedName = patientName.trim();

  const handleSave = async () => {
    if (!currentPatientId || !normalizedName || !onUpdatePatient) {
      return;
    }
    setIsSaving(true);
    try {
      await onUpdatePatient(currentPatientId, normalizedName);
      onClose();
    } finally {
      setIsSaving(false);
    }
  };

  const handleUnlink = async () => {
    if (!onUnlinkEncounter) {
      return;
    }
    setIsSaving(true);
    try {
      await onUnlinkEncounter();
      onClose();
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!onDeletePatient) {
      return;
    }
    setIsSaving(true);
    try {
      await onDeletePatient();
      onClose();
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      data-testid="patient-edit-modal"
    >
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        {!isDeleteConfirmOpen ? (
          <>
            <h2 className="mb-4 text-xl font-semibold">Editar paciente</h2>

            <div className="mb-4">
              <label
                htmlFor="linkedPatientName"
                className="mb-1 block text-sm font-medium text-gray-700"
              >
                Nombre del paciente
              </label>
              <input
                id="linkedPatientName"
                type="text"
                value={patientName}
                onChange={(event) => setPatientName(event.target.value)}
                className="w-full rounded border border-gray-300 p-2 focus:outline-none focus:ring-2 focus:ring-brand-navy"
                placeholder="Nombre del paciente"
                data-testid="connected-name-input"
              />
            </div>

            <div className="mt-6 flex items-center justify-between gap-3 border-t border-gray-100 pt-4">
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 rounded border border-gray-200 px-3 py-2 text-sm font-medium text-red-700 hover:border-red-200 hover:bg-red-50 disabled:opacity-50"
                  onClick={() => setIsDeleteConfirmOpen(true)}
                  disabled={isBusy || !currentPatientId}
                >
                  <Trash2 className="h-4 w-4" />
                  Borrar
                </button>
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 rounded border border-gray-200 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                  onClick={handleUnlink}
                  disabled={isBusy}
                >
                  <Unlink className="h-4 w-4" />
                  Desvincular
                </button>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="rounded bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-50"
                  onClick={onClose}
                  disabled={isBusy}
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  className="rounded bg-brand-purple px-4 py-2 text-sm font-medium text-white hover:bg-brand-purple-dark disabled:bg-purple-300"
                  onClick={handleSave}
                  disabled={!normalizedName || isBusy}
                  data-testid="update-button"
                >
                  {isBusy ? "Guardando..." : "Guardar"}
                </button>
              </div>
            </div>
          </>
        ) : (
          <>
            <h2 className="mb-3 text-xl font-semibold text-red-700">
              Borrar paciente
            </h2>
            <p className="mb-4 text-sm text-slate-700">
              Esta acción borrará el paciente, todos sus encuentros, documentos,
              transcripciones y datos asociados. No se puede deshacer.
            </p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                className="rounded bg-gray-200 px-4 py-2 text-sm font-medium text-gray-800 hover:bg-gray-300 disabled:opacity-50"
                onClick={() => setIsDeleteConfirmOpen(false)}
                disabled={isBusy}
              >
                Cancelar
              </button>
              <button
                type="button"
                className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:bg-red-300"
                onClick={handleDelete}
                disabled={isBusy}
              >
                {isBusy ? "Borrando..." : "Borrar paciente"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default PatientEditModal;
