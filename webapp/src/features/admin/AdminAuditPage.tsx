import { useEffect, useMemo, useState } from "react";

import {
  getInternalAuditEvents,
  type AuditEventFilters,
  type AuditEventItem,
} from "@/api/admin";
import AdminSectionLayout from "./AdminSectionLayout";
import { Badge } from "@/commons/components/ui/badge";
import { Button } from "@/commons/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/commons/components/ui/dialog";
import { Input } from "@/commons/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/commons/components/ui/table";

const PAGE_SIZE = 25;
type BadgeVariant = "default" | "secondary" | "destructive" | "outline";

type AuditFilterState = {
  start_at: string;
  end_at: string;
  action: string;
  result: string;
  actor_id: string;
  session_id: string;
  patient_id: string;
  encounter_id: string;
  document_id: string;
};

const emptyFilters: AuditFilterState = {
  start_at: "",
  end_at: "",
  action: "",
  result: "",
  actor_id: "",
  session_id: "",
  patient_id: "",
  encounter_id: "",
  document_id: "",
};

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString("es-CO", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function resultBadgeVariant(result: string): BadgeVariant {
  if (result === "success") {
    return "default";
  }
  if (result === "denied") {
    return "destructive";
  }
  return "secondary";
}

function normalizeFilters(filters: AuditFilterState): AuditEventFilters {
  return {
    start_at: filters.start_at ? `${filters.start_at}T00:00:00` : undefined,
    end_at: filters.end_at ? `${filters.end_at}T23:59:59` : undefined,
    action: filters.action || undefined,
    result: filters.result || undefined,
    actor_id: filters.actor_id || undefined,
    session_id: filters.session_id || undefined,
    patient_id: filters.patient_id || undefined,
    encounter_id: filters.encounter_id || undefined,
    document_id: filters.document_id || undefined,
  };
}

export default function AdminAuditPage() {
  const [filters, setFilters] = useState<AuditFilterState>(emptyFilters);
  const [appliedFilters, setAppliedFilters] =
    useState<AuditFilterState>(emptyFilters);
  const [items, setItems] = useState<AuditEventItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<AuditEventItem | null>(null);

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  useEffect(() => {
    let isMounted = true;

    async function loadAuditEvents() {
      setLoading(true);
      setError(null);
      try {
        const response = await getInternalAuditEvents({
          ...normalizeFilters(appliedFilters),
          limit: PAGE_SIZE,
          offset,
        });
        if (!isMounted) {
          return;
        }
        setItems(response.items);
        setTotal(response.total);
      } catch {
        if (!isMounted) {
          return;
        }
        setError("No pudimos cargar la auditoria en este momento.");
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    loadAuditEvents();

    return () => {
      isMounted = false;
    };
  }, [appliedFilters, offset]);

  const summaryText = useMemo(() => {
    if (!total) {
      return "Sin eventos para los filtros actuales.";
    }
    const start = offset + 1;
    const end = Math.min(offset + PAGE_SIZE, total);
    return `Mostrando ${start}-${end} de ${total} eventos`;
  }, [offset, total]);

  const handleFilterChange = (field: keyof AuditFilterState, value: string) => {
    setFilters((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setOffset(0);
    setAppliedFilters(filters);
  };

  const handleReset = () => {
    setFilters(emptyFilters);
    setAppliedFilters(emptyFilters);
    setOffset(0);
  };

  return (
    <AdminSectionLayout
      title="Audit Trail"
      description="Vista interna metadata-only para revisar accesos, operaciones y correlacion tecnica sin exponer contenido clinico."
    >
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <form className="grid gap-3 md:grid-cols-2 xl:grid-cols-5" onSubmit={handleSubmit}>
          <Input
            type="date"
            value={filters.start_at}
            onChange={(event) => handleFilterChange("start_at", event.target.value)}
          />
          <Input
            type="date"
            value={filters.end_at}
            onChange={(event) => handleFilterChange("end_at", event.target.value)}
          />
          <Input
            placeholder="Accion"
            value={filters.action}
            onChange={(event) => handleFilterChange("action", event.target.value)}
          />
          <Input
            placeholder="Resultado"
            value={filters.result}
            onChange={(event) => handleFilterChange("result", event.target.value)}
          />
          <Input
            placeholder="Actor ID"
            inputMode="numeric"
            value={filters.actor_id}
            onChange={(event) => handleFilterChange("actor_id", event.target.value)}
          />
          <Input
            placeholder="Session ID"
            value={filters.session_id}
            onChange={(event) => handleFilterChange("session_id", event.target.value)}
          />
          <Input
            placeholder="Patient ID"
            inputMode="numeric"
            value={filters.patient_id}
            onChange={(event) => handleFilterChange("patient_id", event.target.value)}
          />
          <Input
            placeholder="Encounter ID"
            inputMode="numeric"
            value={filters.encounter_id}
            onChange={(event) =>
              handleFilterChange("encounter_id", event.target.value)
            }
          />
          <Input
            placeholder="Document ID"
            inputMode="numeric"
            value={filters.document_id}
            onChange={(event) => handleFilterChange("document_id", event.target.value)}
          />
          <div className="flex items-center gap-2 xl:justify-end">
            <Button type="submit" className="flex-1 xl:flex-none">
              Filtrar
            </Button>
            <Button
              type="button"
              variant="outline"
              className="flex-1 xl:flex-none"
              onClick={handleReset}
            >
              Limpiar
            </Button>
          </div>
        </form>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-2 border-b border-slate-200 px-5 py-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Eventos</h2>
            <p className="text-sm text-slate-600">{summaryText}</p>
          </div>
          <div className="text-xs text-slate-500">
            Solo IDs, snapshots del actor y correlacion tecnica.
          </div>
        </div>

        {error ? (
          <div className="px-5 py-8 text-sm text-red-600">{error}</div>
        ) : (
          <div className="px-2 pb-2">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Fecha</TableHead>
                  <TableHead>Accion</TableHead>
                  <TableHead>Resultado</TableHead>
                  <TableHead>Actor</TableHead>
                  <TableHead>Sesion</TableHead>
                  <TableHead>Recursos</TableHead>
                  <TableHead>Servicio</TableHead>
                  <TableHead className="text-right">Detalle</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!loading && items.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="py-10 text-center text-sm text-slate-500">
                      No hay eventos para los filtros actuales.
                    </TableCell>
                  </TableRow>
                ) : null}
                {items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="min-w-[180px] text-sm text-slate-700">
                      {formatDateTime(item.created_at)}
                    </TableCell>
                    <TableCell className="min-w-[220px] font-medium text-slate-900">
                      {item.action}
                    </TableCell>
                    <TableCell>
                      <Badge variant={resultBadgeVariant(item.result)}>
                        {item.result}
                      </Badge>
                    </TableCell>
                    <TableCell className="min-w-[170px] text-sm text-slate-700">
                      <div>{item.actor_name_snapshot || `ID ${item.actor_id ?? "-"}`}</div>
                      <div className="text-xs text-slate-500">
                        {item.actor_role_snapshot || item.actor_type}
                      </div>
                    </TableCell>
                    <TableCell className="max-w-[180px] truncate text-xs text-slate-600">
                      {item.session_id || "-"}
                    </TableCell>
                    <TableCell className="min-w-[180px] text-xs text-slate-600">
                      <div>Paciente: {item.patient_id ?? "-"}</div>
                      <div>Encuentro: {item.encounter_id ?? "-"}</div>
                      <div>Documento: {item.document_id ?? "-"}</div>
                    </TableCell>
                    <TableCell className="min-w-[180px] text-xs text-slate-600">
                      <div>{item.service_name || "-"}</div>
                      <div>{item.error_code || "-"}</div>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setSelectedEvent(item)}
                      >
                        Ver
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={8} className="py-10 text-center text-sm text-slate-500">
                      Cargando eventos...
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </div>
        )}

        <div className="flex flex-col gap-3 border-t border-slate-200 px-5 py-4 md:flex-row md:items-center md:justify-between">
          <p className="text-sm text-slate-600">
            Pagina {page} de {totalPages}
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
              disabled={offset === 0 || loading}
            >
              Anterior
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() =>
                setOffset((current) =>
                  current + PAGE_SIZE >= total ? current : current + PAGE_SIZE,
                )
              }
              disabled={offset + PAGE_SIZE >= total || loading}
            >
              Siguiente
            </Button>
          </div>
        </div>
      </section>

      <Dialog
        open={selectedEvent !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedEvent(null);
          }
        }}
      >
        <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Detalle tecnico del evento</DialogTitle>
            <DialogDescription>
              Metadata de auditoria para correlacion operativa. Sin contenido clinico.
            </DialogDescription>
          </DialogHeader>
          {selectedEvent ? (
            <div className="grid gap-4 md:grid-cols-2">
              {[
                ["Fecha", formatDateTime(selectedEvent.created_at)],
                ["Accion", selectedEvent.action],
                ["Resultado", selectedEvent.result],
                ["Actor", selectedEvent.actor_name_snapshot || "-"],
                ["Actor ID", selectedEvent.actor_id?.toString() || "-"],
                ["Rol actor", selectedEvent.actor_role_snapshot || "-"],
                ["Actor type", selectedEvent.actor_type],
                ["Session ID", selectedEvent.session_id || "-"],
                ["Patient ID", selectedEvent.patient_id?.toString() || "-"],
                ["Encounter ID", selectedEvent.encounter_id?.toString() || "-"],
                ["Document ID", selectedEvent.document_id?.toString() || "-"],
                ["Resource type", selectedEvent.resource_type || "-"],
                ["Resource ID", selectedEvent.resource_id || "-"],
                ["Service", selectedEvent.service_name || "-"],
                ["Service account", selectedEvent.service_account || "-"],
                ["Error code", selectedEvent.error_code || "-"],
                ["Trace ID", selectedEvent.trace_id || "-"],
                ["Request ID", selectedEvent.request_id || "-"],
              ].map(([label, value]) => (
                <div key={label} className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
                  <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
                    {label}
                  </div>
                  <div className="mt-1 break-all text-sm text-slate-900">{value}</div>
                </div>
              ))}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </AdminSectionLayout>
  );
}
