import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/commons/hooks/useAuth";
import { cn } from "@/lib/utils";
import { Button } from "@/commons/components/ui/button";
import { Input } from "@/commons/components/ui/input";
import { Label } from "@/commons/components/ui/label";

// Logger utility for consistent logging
const logForm = (type: "info" | "error", message: string, data?: any) => {
  const prefix = "[LoginForm]";
  if (type === "info") {
    console.log(`${prefix} ${message}`, data || "");
  } else {
    console.error(`${prefix} ${message}`, data || "");
  }
};

export function LoginForm(props: React.ComponentPropsWithoutRef<"form">) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { login, error, loading } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      logForm("info", "Submitting login form", { email });
      await login(email, password);
      logForm("info", "Login successful, redirecting to dashboard");
      // No need to redirect here - AuthContext will handle it
    } catch (err) {
      logForm("error", "Form submission error");
      // Error already handled by useAuth
    }
  };

  const handleRedirect = (path: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    logForm("info", "Redirecting to", path);
    navigate(path);
  };

  return (
    <form
      className={cn("flex flex-col gap-6", props.className)}
      onSubmit={handleSubmit}
      {...props}
    >
      {/* Brand logo - with less top margin */}
      <div className="flex justify-center w-full mt-0">
        <div className="relative w-full max-w-[280px] aspect-square">
          <img
            src="/brand_logo_no_text.png"
            alt="Brand Logo"
            className="object-contain w-full h-full"
          />
        </div>
      </div>
      <div className="flex flex-col items-center gap-2 text-center">
        <h1 className="text-2xl font-bold text-main font-fun tracking-tight">
          Bienvenido
        </h1>
        <p className="text-balance text-sm text-neutral-600 dark:text-neutral-300">
          Ingresa con tus credenciales para acceder a los servicios médicos
        </p>
      </div>
      <div className="grid gap-7">
        {error && (
          <div className="p-4 text-sm font-medium text-red-500 bg-red-50 border border-red-100 rounded-md dark:bg-red-900/20 dark:border-red-900/30">
            {error}
          </div>
        )}
        <div className="grid gap-2.5">
          <Label
            htmlFor="email"
            className="font-medium text-neutral-700 dark:text-neutral-200"
          >
            Email
          </Label>
          <Input
            id="email"
            type="email"
            placeholder="m@example.com"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="py-2.5"
          />
        </div>
        <div className="grid gap-2.5">
          <div className="flex items-center">
            <Label
              htmlFor="password"
              className="font-medium text-neutral-700 dark:text-neutral-200"
            >
              Password
            </Label>
            <Link
              to="/forgot-password"
              className="ml-auto text-sm text-main hover:text-main_dark underline-offset-4 hover:underline transition-colors"
            >
              ¿Olvidaste tu contraseña?
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
          className="w-full bg-blue-500 hover:bg-main_dark text-white font-medium py-6 mt-2 transition-colors"
          disabled={loading}
        >
          {loading ? "Iniciando sesión..." : "Iniciar Sesión"}
        </Button>
      </div>
      <div className="text-center text-sm mt-2">
        ¿No tienes una cuenta?{" "}
        <Link
          to="/registro"
          className="font-medium text-main hover:text-main_dark underline underline-offset-4 transition-colors"
        >
          Regístrate
        </Link>
      </div>
    </form>
  );
}
