import Reveal from "./Reveal";

const steps = [
  {
    number: "01",
    title: "Grabas la consulta",
    description: "Presiona grabar y atiende con normalidad.",
  },
  {
    number: "02",
    title: "Notia transcribe y redacta",
    description: "Genera la transcripción y un borrador de nota clínica.",
  },
  {
    number: "03",
    title: "Revisas y copias",
    description: "Editas y copias por secciones a tu historia clínica.",
  },
];

export default function HowItWorksSection() {
  return (
    <section className="px-4 py-20 md:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <div className="rounded-3xl bg-violet-50 px-6 py-12 md:px-12 md:py-16">
            <h2 className="text-3xl font-bold tracking-tight text-slate-900 md:text-5xl">
              De consulta a borrador clínico en 3 pasos.
            </h2>

            <div className="mt-10 grid items-center gap-10 md:grid-cols-2 md:gap-14">
              {/* Steps */}
              <ol className="space-y-8">
                {steps.map((step) => (
                  <li key={step.number} className="flex gap-5">
                    <span className="text-4xl font-bold leading-none text-brand md:text-5xl">
                      {step.number}
                    </span>
                    <div>
                      <h3 className="text-xl font-semibold text-slate-900">
                        {step.title}
                      </h3>
                      <p className="mt-1 text-slate-600 leading-snug">
                        {step.description}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>

              {/* Product mockup placeholder */}
              <div className="relative aspect-[4/3] w-full overflow-hidden rounded-2xl border border-white bg-white shadow-lg">
                <div className="flex items-center gap-1.5 border-b border-slate-100 px-4 py-3">
                  <span className="h-2.5 w-2.5 rounded-full bg-slate-200" />
                  <span className="h-2.5 w-2.5 rounded-full bg-slate-200" />
                  <span className="h-2.5 w-2.5 rounded-full bg-slate-200" />
                </div>
                <div className="flex h-full items-center justify-center">
                  <span className="text-sm font-medium uppercase tracking-wide text-slate-300">
                    Mockup del producto
                  </span>
                </div>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
