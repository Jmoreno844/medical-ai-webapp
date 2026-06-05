import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/commons/hooks/useAuth";
import { cn } from "@/lib/utils";
import { Button } from "@/commons/components/ui/button";
import { Input } from "@/commons/components/ui/input";
import { Label } from "@/commons/components/ui/label";

// Logger utility for consistent logging
import { logger } from "@/lib/logger";
const logForm = (type: "info" | "error", message: string, data?: any) => {
  const prefix = "[LoginForm]";
  if (type === "info") {
    logger.debug(`${prefix} ${message}`, data || "");
  } else {
    logger.error(`${prefix} ${message}`, data || "");
  }
};

export function LoginForm(props: React.ComponentPropsWithoutRef<"form">) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { login, error, loading } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      logForm("info", "Submitting login form", { email });
      await login(email, password);
      logForm("info", "Login successful, redirecting to dashboard");
    } catch (err) {
      logForm("error", "Form submission error");
      // Error already handled by useAuth
    }
  };

  return (
    <form
      className={cn("flex flex-col gap-5", props.className)}
      onSubmit={handleSubmit}
      {...props}
    >
      {/* Brand logo - with less top margin */}
      <div className="flex justify-center w-full mt-0">
        <div className="relative w-full max-w-[9rem] aspect-square">
          <img
            src="/brand_logo_no_text.png"
            alt="Logotipo"
            className="object-contain w-full h-full"
          />
        </div>
      </div>
      <div className="flex flex-col items-center gap-1.5 text-center">
        <h1 className="text-xl font-bold text-main font-fun tracking-tight">
          Bienvenido/a
        </h1>
        <p className="text-balance text-sm text-neutral-600 dark:text-neutral-300">
          Introduzca sus credenciales para acceder
        </p>
      </div>
      <div className="grid gap-5">
        {error && (
          <div className="p-3 text-sm font-medium text-red-500 bg-red-50 border border-red-100 rounded-md dark:bg-red-900/20 dark:border-red-900/30">
            {error}
          </div>
        )}
        <div className="grid gap-2">
          <Label
            htmlFor="email"
            className="font-medium text-neutral-700 dark:text-neutral-200"
          >
            Correo electrónico
          </Label>
          <Input
            id="email"
            type="email"
            placeholder="correo@ejemplo.com"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="py-2.5"
          />
        </div>
        <div className="grid gap-2">
          <div className="flex items-center">
            <Label
              htmlFor="password"
              className="font-medium text-neutral-700 dark:text-neutral-200"
            >
              Contraseña
            </Label>
            <Link
              to="/forgot-password"
              className="ml-auto text-sm text-main hover:text-main_dark underline-offset-4 hover:underline transition-colors"
            >
              ¿Olvidó su contraseña?
            </Link>
          </div>
          <Input
            id="password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="py-2.5"
          />
        </div>
        <Button
          type="submit"
          className="w-full bg-blue-500 hover:bg-main_dark text-white font-medium mt-1 transition-colors"
          disabled={loading}
        >
          {loading ? "Entrando…" : "Iniciar sesión"}
        </Button>
      </div>
      <div className="text-center text-sm mt-2">
        ¿No tiene cuenta?{" "}
        <Link
          to="/registro"
          className="font-medium text-main hover:text-main_dark underline underline-offset-4 transition-colors"
        >
          Registrarse
        </Link>
      </div>
    </form>
  );
}
