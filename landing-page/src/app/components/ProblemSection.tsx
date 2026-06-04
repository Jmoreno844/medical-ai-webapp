import { Button } from "@/components/ui/button";
import Reveal from "./Reveal";

export default function ProblemSection() {
  return (
    <section className="px-4 py-20 md:py-28 md:pl-20 lg:pl-32 xl:pl-44">
      <Reveal className="grid max-w-6xl items-start gap-x-12 gap-y-8 md:grid-cols-[3fr_2fr]">
        {/* Left: headline + CTAs */}
        <div>
          <h2 className="text-4xl font-bold tracking-tight text-slate-900 md:text-6xl">
            La documentación no debería alargar tu jornada.
          </h2>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <a href="#">
              <Button
                size="lg"
                className="h-12 rounded-full bg-brand px-8 text-brand-foreground hover:bg-brand/90"
              >
                Empieza gratis
              </Button>
            </a>
            <a href="#">
              <Button
                size="lg"
                variant="secondary"
                className="h-12 rounded-full px-8"
              >
                Agenda una demo
              </Button>
            </a>
          </div>
        </div>

        {/* Right: supporting copy */}
        <p className="text-slate-800 md:pt-3 md:text-xl leading-snug">
          Entre escribir durante la consulta, completar notas después y copiar
          información entre sistemas, la documentación clínica termina robando
          tiempo que podría ser para tus pacientes, tu equipo o tu vida fuera del
          consultorio.
        </p>
      </Reveal>
    </section>
  );
}
