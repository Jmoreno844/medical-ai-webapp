import { Button } from "@/components/ui/button";

export default function Navbar() {
  return (
    <header className="w-full">
      <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 md:px-6">
        {/* Brand */}
        <a href="#home" className="text-xl font-bold tracking-tight text-slate-900">
          Notia
        </a>

        {/* Links */}
        <div className="hidden items-center gap-8 md:flex">
          <a
            href="#home"
            className="text-sm font-medium text-slate-600 transition-colors hover:text-slate-900"
          >
            Home
          </a>
          <a
            href="#precios"
            className="text-sm font-medium text-slate-600 transition-colors hover:text-slate-900"
          >
            Precios
          </a>
        </div>

        {/* CTA */}
        <a href="#">
          <Button className="rounded-full bg-brand px-5 text-brand-foreground hover:bg-brand/90">
            Ir a la app
          </Button>
        </a>
      </nav>
    </header>
  );
}
