import { useContext, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import { Loader2, ChevronRight, Mic, ArrowRight } from "lucide-react";
import { AuthContext } from "@/commons/contexts/AuthContext";
import { Button } from "@/commons/components/ui/button";
import useEncuentroList from "../app_layout/hooks/Encuentros/useEncuentroList";
import { useNuevoEncuentro } from "../app_layout/hooks/Encuentros/useNuevoEncuentro";

const PLACEHOLDER_NAMES = new Set(["Encuentro Nuevo", "New Encounter", ""]);

export default function EncuentroPage() {
  const { encuentros, loading, error } = useEncuentroList();
  const { crearNuevoEncuentro, loading: creating } = useNuevoEncuentro();
  const { userData } = useContext(AuthContext);
  const navigate = useNavigate();

  const lastName = userData?.last_name?.trim();

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
    <div className="container mx-auto max-w-6xl px-4 sm:px-6 py-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        {/* Left: welcome + primary action */}
        <div className="space-y-5">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold">
              Bienvenido/a{lastName ? `, Dr./Dra. ${lastName}` : ""}
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Concéntrese en el paciente; de la documentación nos encargamos
              nosotros.
            </p>
          </div>

          <div className="rounded-xl bg-gradient-to-br from-purple-600 to-purple-700 text-white p-6 shadow-sm">
            <div className="flex items-center justify-center h-11 w-11 rounded-full bg-white/15">
              <Mic className="h-5 w-5" />
            </div>
            <h2 className="text-lg font-semibold mt-4">Nueva consulta</h2>
            <p className="text-sm text-white/85 mt-1 max-w-md">
              Grabe o suba el audio de la consulta y genere notas clínicas en
              minutos.
            </p>
            <Button
              onClick={() => void crearNuevoEncuentro()}
              disabled={creating}
              className="mt-5 bg-white text-purple-700 hover:bg-purple-50 font-semibold"
            >
              {creating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowRight className="h-4 w-4" />
              )}
              {creating ? "Creando…" : "Empezar"}
            </Button>
          </div>
        </div>

        {/* Right: recent encounters */}
        <aside className="lg:sticky lg:top-6 self-start">
          <div className="rounded-xl border bg-card overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <h2 className="font-semibold text-sm">Encuentros recientes</h2>
              {!loading && !error && ordered.length > 0 && (
                <span className="text-xs text-muted-foreground tabular-nums">
                  {ordered.length}
                </span>
              )}
            </div>

            {loading ? (
              <div className="flex justify-center items-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
              </div>
            ) : error ? (
              <div className="m-3 bg-red-50 p-3 rounded-md text-sm text-red-800">
                {error}
              </div>
            ) : ordered.length === 0 ? (
              <div className="px-4 py-10 text-center">
                <p className="text-sm font-medium">Aún no tiene encuentros</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Cree una consulta para empezar.
                </p>
              </div>
            ) : (
              <div className="p-2 space-y-1 max-h-[70vh] overflow-y-auto">
                {ordered.map((encuentro) => (
                  <button
                    key={encuentro.id}
                    type="button"
                    onClick={() => navigate(`/encuentro/${encuentro.id}`)}
                    className="group flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left transition-colors hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">
                        {displayName(encuentro.encounter_name)}
                      </span>
                      <span className="block text-xs text-muted-foreground mt-0.5">
                        {formatDateTime(encuentro.occurred_at)}
                      </span>
                    </span>
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/60 group-hover:text-muted-foreground" />
                  </button>
                ))}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
