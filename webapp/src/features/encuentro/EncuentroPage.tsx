import { useContext, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import {
  ArrowRight,
  CalendarClock,
  ChevronRight,
  Loader2,
  Mic,
  Stethoscope,
} from "lucide-react";
import { AuthContext } from "@/commons/contexts/AuthContext";
import { Button } from "@/commons/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/commons/components/ui/card";
import useEncuentroList from "../app_layout/hooks/Encuentros/useEncuentroList";
import { useNuevoEncuentro } from "../app_layout/hooks/Encuentros/useNuevoEncuentro";

const PLACEHOLDER_NAMES = new Set(["Encuentro Nuevo", "New Encounter", ""]);

const getGreeting = () => {
  const hour = new Date().getHours();
  if (hour < 12) return "Buenos días";
  if (hour < 20) return "Buenas tardes";
  return "Buenas noches";
};

export default function EncuentroPage() {
  const { encuentros, loading, error } = useEncuentroList();
  const { crearNuevoEncuentro, loading: creating } = useNuevoEncuentro();
  const { userData } = useContext(AuthContext);
  const navigate = useNavigate();

  const lastName = userData?.last_name?.trim();
  const greeting = getGreeting();

  // Most recent first
  const ordered = useMemo(
    () =>
      [...encuentros].sort(
        (a, b) =>
          new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime()
      ),
    [encuentros]
  );

  const formatDateTime = (value: string) => {
    try {
      return format(new Date(value), "dd MMM yyyy · HH:mm", { locale: es });
    } catch {
      return value;
    }
  };

  const displayName = (name: string) =>
    PLACEHOLDER_NAMES.has(name?.trim()) ? "Encuentro sin título" : name;

  return (
    <div className="container mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-10">
      <div className="rounded-3xl border border-slate-200 bg-gradient-to-br from-slate-50 via-white to-sky-50/60 p-6 shadow-sm sm:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
              Inicio
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
              {greeting}
              {lastName ? `, Dr./Dra. ${lastName}` : ""}
            </h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600 sm:text-base">
              Cree una nueva consulta o retome un encuentro reciente. Esta
              pantalla debe ayudarle a empezar rapido, no distraerle.
            </p>
          </div>

          <Card className="border-slate-200 bg-white/95 shadow-md lg:max-w-sm">
            <CardHeader className="pb-4">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-sky-100 text-sky-700">
                <Mic className="h-5 w-5" />
              </div>
              <CardTitle className="text-xl text-slate-900">
                Nueva consulta
              </CardTitle>
              <CardDescription className="text-sm leading-6 text-slate-600">
                Inicie un encuentro, grabe o suba el audio y continue luego con
                la documentacion clinica.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 rounded-xl bg-white p-2 text-slate-700 shadow-sm">
                    <Stethoscope className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-900">
                      Flujo recomendado
                    </p>
                    <p className="mt-1 text-sm leading-6 text-slate-600">
                      Abra la consulta, capture el audio y retome despues la
                      nota desde el encuentro.
                    </p>
                  </div>
                </div>
              </div>

              <Button
                onClick={() => void crearNuevoEncuentro()}
                disabled={creating}
                size="lg"
                className="w-full bg-slate-900 text-white hover:bg-slate-800"
              >
                {creating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ArrowRight className="h-4 w-4" />
                )}
                {creating ? "Creando consulta..." : "Crear nueva consulta"}
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="mt-8">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">
              Encuentros recientes
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              Retome una consulta previa o revise las ultimas atenciones.
            </p>
          </div>
          {!loading && !error && ordered.length > 0 && (
            <div className="hidden rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 tabular-nums sm:block">
              {ordered.length} recientes
            </div>
          )}
        </div>

        {loading ? (
          <div className="flex items-center justify-center rounded-2xl border bg-card py-16">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            {error}
          </div>
        ) : ordered.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white py-14 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-600">
              <CalendarClock className="h-5 w-5" />
            </div>
            <p className="mt-4 text-base font-medium text-slate-900">
              Aun no hay encuentros registrados
            </p>
            <p className="mt-2 text-sm text-slate-600">
              Cree una nueva consulta para empezar a trabajar desde aqui.
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            {ordered.map((encuentro) => (
              <button
                key={encuentro.id}
                type="button"
                onClick={() => navigate(`/encuentro/${encuentro.id}`)}
                className="group flex w-full items-center justify-between gap-4 border-b border-slate-100 px-5 py-4 text-left transition-colors last:border-b-0 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex min-w-0 items-start gap-3">
                  <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                    <Stethoscope className="h-4 w-4" />
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-slate-900 sm:text-base">
                      {displayName(encuentro.encounter_name)}
                    </span>
                    <span className="mt-1 block text-xs uppercase tracking-[0.18em] text-slate-500">
                      Encuentro
                    </span>
                    <span className="mt-1 block text-sm text-slate-600">
                      {formatDateTime(encuentro.occurred_at)}
                    </span>
                  </span>
                </span>
                <span className="flex items-center gap-2 text-sm text-slate-500">
                  <span className="hidden sm:inline">Abrir</span>
                  <ChevronRight className="h-4 w-4 shrink-0 text-slate-400 transition-transform group-hover:translate-x-0.5 group-hover:text-slate-600" />
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
