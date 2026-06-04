import { Button } from "@/components/ui/button";
import { Play } from "lucide-react";

export default function HeroSection() {
  return (
    <section className="px-4 py-6 md:py-8">
      <div className="mx-auto max-w-6xl overflow-hidden rounded-3xl bg-hero-violet px-6 py-12 md:px-12 md:py-16">
        <div className="grid items-center gap-10 md:grid-cols-2">
          {/* Left column: copy + CTA */}
          <div className="flex flex-col items-start gap-6">
            <h1 className="text-4xl font-bold tracking-tight text-slate-900 md:text-6xl">
              Recupera tu tiempo libre. Hasta 20 horas por semana.
            </h1>
            <p className="max-w-md text-slate-700 md:text-lg">
              Notia escucha la consulta, transcribe la conversación y genera un
              borrador de nota clínica para que lo revises, edites y copies a tu
              historia clínica.
            </p>
            <a href="#">
              <Button
                size="lg"
                className="h-12 rounded-full bg-brand px-8 text-brand-foreground hover:bg-brand/90"
              >
                Descarga la app
              </Button>
            </a>
          </div>

          {/* Right column: media placeholder */}
          <div className="relative aspect-video w-full overflow-hidden rounded-2xl border border-white/40 bg-slate-200/60 shadow-lg">
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-sm font-medium uppercase tracking-wide text-slate-400">
                Placeholder
              </span>
            </div>
            <div className="absolute bottom-4 right-4 flex h-11 w-11 items-center justify-center rounded-full bg-white/90 shadow-md">
              <Play className="h-5 w-5 fill-slate-900 text-slate-900" />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
