import { useEffect, useMemo, useState } from "react";

import {
  getInternalUserDetail,
  getInternalUsers,
  updateInternalUserStatus,
  type AdminUserDetailResponse,
  type AdminUserListItem,
} from "@/api/admin";
import { useAuth } from "@/commons/hooks/useAuth";
import AdminSectionLayout from "./AdminSectionLayout";
import { Badge } from "@/commons/components/ui/badge";
import { Button } from "@/commons/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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

const PAGE_SIZE = 20;

type UserFilterState = {
  q: string;
  role: string;
  is_active: string;
};

const emptyFilters: UserFilterState = {
  q: "",
  role: "",
  is_active: "",
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

export default function AdminUsersPage() {
  const { userData, capabilities } = useAuth();
  const [filters, setFilters] = useState<UserFilterState>(emptyFilters);
  const [appliedFilters, setAppliedFilters] =
    useState<UserFilterState>(emptyFilters);
  const [items, setItems] = useState<AdminUserListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [selectedUserDetail, setSelectedUserDetail] =
    useState<AdminUserDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [statusSaving, setStatusSaving] = useState(false);

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  useEffect(() => {
    let isMounted = true;

    async function loadUsers() {
      setLoading(true);
      setError(null);
      try {
        const response = await getInternalUsers({
          q: appliedFilters.q || undefined,
          role: appliedFilters.role || undefined,
          is_active: appliedFilters.is_active || undefined,
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
        setError("No pudimos cargar los usuarios internos.");
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    loadUsers();

    return () => {
      isMounted = false;
    };
  }, [appliedFilters, offset]);

  useEffect(() => {
    if (selectedUserId === null) {
      setSelectedUserDetail(null);
      setDetailError(null);
      return;
    }

    const currentUserId = selectedUserId;
    let isMounted = true;

    async function loadDetail() {
      setDetailLoading(true);
      setDetailError(null);
      try {
        const response = await getInternalUserDetail(currentUserId);
        if (!isMounted) {
          return;
        }
        setSelectedUserDetail(response);
      } catch {
        if (!isMounted) {
          return;
        }
        setDetailError("No pudimos cargar el detalle del usuario.");
      } finally {
        if (isMounted) {
          setDetailLoading(false);
        }
      }
    }

    loadDetail();

    return () => {
      isMounted = false;
    };
  }, [selectedUserId]);

  const summaryText = useMemo(() => {
    if (!total) {
      return "Sin usuarios para los filtros actuales.";
    }
    const start = offset + 1;
    const end = Math.min(offset + PAGE_SIZE, total);
    return `Mostrando ${start}-${end} de ${total} usuarios`;
  }, [offset, total]);

  const handleFilterChange = (field: keyof UserFilterState, value: string) => {
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

  const refreshCurrentPage = async () => {
    const response = await getInternalUsers({
      q: appliedFilters.q || undefined,
      role: appliedFilters.role || undefined,
      is_active: appliedFilters.is_active || undefined,
      limit: PAGE_SIZE,
      offset,
    });
    setItems(response.items);
    setTotal(response.total);
  };

  const handleToggleStatus = async () => {
    if (!selectedUserDetail) {
      return;
    }

    setStatusSaving(true);
    setDetailError(null);
    try {
      await updateInternalUserStatus(
        selectedUserDetail.user.id,
        !selectedUserDetail.user.is_active,
      );
      const updatedDetail = await getInternalUserDetail(selectedUserDetail.user.id);
      setSelectedUserDetail(updatedDetail);
      await refreshCurrentPage();
    } catch {
      setDetailError("No pudimos actualizar el estado del usuario.");
    } finally {
      setStatusSaving(false);
    }
  };

  return (
    <AdminSectionLayout
      title="Usuarios"
      description="Vista interna para revisar cuentas medicas, actividad resumida y estado operativo sin exponer secretos ni contenido clinico."
    >
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <form className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" onSubmit={handleSubmit}>
          <Input
            placeholder="Buscar por nombre o email"
            value={filters.q}
            onChange={(event) => handleFilterChange("q", event.target.value)}
          />
          <Input
            placeholder="Rol"
            value={filters.role}
            onChange={(event) => handleFilterChange("role", event.target.value)}
          />
          <Input
            placeholder="Estado: true / false"
            value={filters.is_active}
            onChange={(event) =>
              handleFilterChange("is_active", event.target.value.trim().toLowerCase())
            }
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
            <h2 className="text-lg font-semibold text-slate-900">Cuentas</h2>
            <p className="text-sm text-slate-600">{summaryText}</p>
          </div>
          <div className="text-xs text-slate-500">
            Muestra identidad del usuario medico, sesiones resumidas y metricas operativas.
          </div>
        </div>

        {error ? (
          <div className="px-5 py-8 text-sm text-red-600">{error}</div>
        ) : (
          <div className="px-2 pb-2">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Usuario</TableHead>
                  <TableHead>Rol</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Ultimo login</TableHead>
                  <TableHead>Sesiones activas</TableHead>
                  <TableHead>Logins 24h</TableHead>
                  <TableHead className="text-right">Detalle</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!loading && items.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="py-10 text-center text-sm text-slate-500">
                      No hay usuarios para los filtros actuales.
                    </TableCell>
                  </TableRow>
                ) : null}
                {items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="min-w-[230px]">
                      <div className="font-medium text-slate-900">
                        {item.name} {item.last_name}
                      </div>
                      <div className="text-sm text-slate-600">{item.email}</div>
                    </TableCell>
                    <TableCell className="text-sm text-slate-700">{item.role}</TableCell>
                    <TableCell>
                      <Badge variant={item.is_active ? "default" : "secondary"}>
                        {item.is_active ? "Activa" : "Inactiva"}
                      </Badge>
                    </TableCell>
                    <TableCell className="min-w-[180px] text-sm text-slate-700">
                      {formatDateTime(item.last_login)}
                    </TableCell>
                    <TableCell className="text-sm text-slate-700">
                      {item.active_session_count}
                    </TableCell>
                    <TableCell className="text-sm text-slate-700">
                      {item.login_success_24h} ok / {item.login_failure_24h} fail
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setSelectedUserId(item.id)}
                      >
                        Ver
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={7} className="py-10 text-center text-sm text-slate-500">
                      Cargando usuarios...
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
        open={selectedUserId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedUserId(null);
          }
        }}
      >
        <DialogContent className="max-h-[85vh] max-w-5xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Detalle de usuario</DialogTitle>
            <DialogDescription>
              Informacion operativa del usuario y sus sesiones recientes.
            </DialogDescription>
          </DialogHeader>

          {detailError ? <div className="text-sm text-red-600">{detailError}</div> : null}

          {detailLoading && !selectedUserDetail ? (
            <div className="py-10 text-sm text-slate-500">Cargando detalle...</div>
          ) : null}

          {selectedUserDetail ? (
            <div className="space-y-6">
              <section className="grid gap-4 md:grid-cols-4">
                <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Usuario</div>
                  <div className="mt-1 text-sm font-medium text-slate-900">
                    {selectedUserDetail.user.name} {selectedUserDetail.user.last_name}
                  </div>
                  <div className="mt-1 text-sm text-slate-600">
                    {selectedUserDetail.user.email}
                  </div>
                </div>
                <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Rol</div>
                  <div className="mt-1 text-sm font-medium text-slate-900">
                    {selectedUserDetail.user.role}
                  </div>
                </div>
                <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Estado</div>
                  <div className="mt-1">
                    <Badge
                      variant={selectedUserDetail.user.is_active ? "default" : "secondary"}
                    >
                      {selectedUserDetail.user.is_active ? "Activa" : "Inactiva"}
                    </Badge>
                  </div>
                </div>
                <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
                  <div className="text-xs uppercase tracking-wide text-slate-500">
                    Ultimo login
                  </div>
                  <div className="mt-1 text-sm font-medium text-slate-900">
                    {formatDateTime(selectedUserDetail.user.last_login)}
                  </div>
                </div>
              </section>

              <section className="grid gap-4 md:grid-cols-4">
                <div className="rounded-md border border-slate-200 bg-white px-4 py-3">
                  <div className="text-xs uppercase tracking-wide text-slate-500">
                    Sesiones activas
                  </div>
                  <div className="mt-1 text-lg font-semibold text-slate-900">
                    {selectedUserDetail.user.active_session_count}
                  </div>
                </div>
                <div className="rounded-md border border-slate-200 bg-white px-4 py-3">
                  <div className="text-xs uppercase tracking-wide text-slate-500">
                    Ultima sesion
                  </div>
                  <div className="mt-1 text-sm font-medium text-slate-900">
                    {formatDateTime(selectedUserDetail.user.last_session_started_at)}
                  </div>
                </div>
                <div className="rounded-md border border-slate-200 bg-white px-4 py-3">
                  <div className="text-xs uppercase tracking-wide text-slate-500">
                    Login ok 24h
                  </div>
                  <div className="mt-1 text-lg font-semibold text-slate-900">
                    {selectedUserDetail.user.login_success_24h}
                  </div>
                </div>
                <div className="rounded-md border border-slate-200 bg-white px-4 py-3">
                  <div className="text-xs uppercase tracking-wide text-slate-500">
                    Login fail 24h
                  </div>
                  <div className="mt-1 text-lg font-semibold text-slate-900">
                    {selectedUserDetail.user.login_failure_24h}
                  </div>
                </div>
              </section>

              <section className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-semibold text-slate-900">Sesiones recientes</h3>
                  <div className="text-xs text-slate-500">
                    Solo IP HMAC y prefijo de red. Nunca IP completa.
                  </div>
                </div>
                <div className="rounded-lg border border-slate-200">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Inicio</TableHead>
                        <TableHead>Ultima actividad</TableHead>
                        <TableHead>Fin</TableHead>
                        <TableHead>Prefijo red</TableHead>
                        <TableHead>IP HMAC</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {selectedUserDetail.sessions.length === 0 ? (
                        <TableRow>
                          <TableCell
                            colSpan={5}
                            className="py-8 text-center text-sm text-slate-500"
                          >
                            Sin sesiones recientes.
                          </TableCell>
                        </TableRow>
                      ) : null}
                      {selectedUserDetail.sessions.map((session) => (
                        <TableRow key={session.id}>
                          <TableCell>{formatDateTime(session.started_at)}</TableCell>
                          <TableCell>{formatDateTime(session.last_seen_at)}</TableCell>
                          <TableCell>{formatDateTime(session.ended_at)}</TableCell>
                          <TableCell>{session.network_prefix || "-"}</TableCell>
                          <TableCell className="max-w-[220px] truncate text-xs text-slate-600">
                            {session.ip_hmac}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </section>

              <section className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-semibold text-slate-900">
                    Eventos recientes del usuario
                  </h3>
                  <div className="text-xs text-slate-500">
                    Solo IDs clinicos, acciones y correlacion tecnica.
                  </div>
                </div>
                <div className="rounded-lg border border-slate-200">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Fecha</TableHead>
                        <TableHead>Accion</TableHead>
                        <TableHead>Resultado</TableHead>
                        <TableHead>Documento</TableHead>
                        <TableHead>Encounter</TableHead>
                        <TableHead>Trace</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {selectedUserDetail.recent_events.length === 0 ? (
                        <TableRow>
                          <TableCell
                            colSpan={6}
                            className="py-8 text-center text-sm text-slate-500"
                          >
                            Sin eventos recientes.
                          </TableCell>
                        </TableRow>
                      ) : null}
                      {selectedUserDetail.recent_events.map((event) => (
                        <TableRow key={event.id}>
                          <TableCell>{formatDateTime(event.created_at)}</TableCell>
                          <TableCell className="font-medium text-slate-900">
                            {event.action}
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant={event.result === "success" ? "default" : "secondary"}
                            >
                              {event.result}
                            </Badge>
                          </TableCell>
                          <TableCell>{event.document_id ?? "-"}</TableCell>
                          <TableCell>{event.encounter_id ?? "-"}</TableCell>
                          <TableCell className="max-w-[220px] truncate text-xs text-slate-600">
                            {event.trace_id || "-"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </section>
            </div>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={handleToggleStatus}
              disabled={
                !capabilities.can_manage_users ||
                !selectedUserDetail ||
                selectedUserDetail.user.id === userData?.id ||
                statusSaving
              }
            >
              {statusSaving
                ? "Guardando..."
                : selectedUserDetail?.user.is_active
                  ? "Desactivar cuenta"
                  : "Activar cuenta"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AdminSectionLayout>
  );
}
