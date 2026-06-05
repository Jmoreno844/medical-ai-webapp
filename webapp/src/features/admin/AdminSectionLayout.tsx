import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";
import { Badge } from "@/commons/components/ui/badge";

type AdminSectionLayoutProps = {
  title: string;
  description: string;
  children: React.ReactNode;
};

const tabs = [
  { label: "Audit Trail", to: "/admin/audit" },
  { label: "Usuarios", to: "/admin/users" },
];

export default function AdminSectionLayout({
  title,
  description,
  children,
}: AdminSectionLayoutProps) {
  return (
    <div className="min-h-screen bg-slate-50 px-4 py-6 md:px-6 lg:px-8">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <section className="rounded-lg border border-slate-200 bg-white px-5 py-5 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="space-y-2">
              <Badge
                variant="outline"
                className="w-fit border-slate-300 bg-slate-100 text-slate-700"
              >
                Panel interno
              </Badge>
              <div className="space-y-1">
                <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
                <p className="max-w-3xl text-sm text-slate-600">{description}</p>
              </div>
            </div>
            <nav className="flex flex-wrap gap-2">
              {tabs.map((tab) => (
                <NavLink
                  key={tab.to}
                  to={tab.to}
                  className={({ isActive }) =>
                    cn(
                      "inline-flex h-10 items-center rounded-md border px-4 text-sm font-medium transition-colors",
                      isActive
                        ? "border-slate-900 bg-slate-900 text-white"
                        : "border-slate-200 bg-white text-slate-700 hover:bg-slate-100",
                    )
                  }
                >
                  {tab.label}
                </NavLink>
              ))}
            </nav>
          </div>
        </section>
        {children}
      </div>
    </div>
  );
}
