import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/commons/hooks/useAuth";
import { cn } from "@/lib/utils";
import { Button } from "@/commons/components/ui/button";
import { Input } from "@/commons/components/ui/input";
import { Label } from "@/commons/components/ui/label";
import appLogo from "@/assets/icon.svg";

export function SignupForm(props: React.ComponentPropsWithoutRef<"form">) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [lastName, setLastName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const { signUp, loading } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password.length < 8) {
      setError("La contraseña debe tener al menos 8 caracteres");
      return;
    }

    if (password !== confirmPassword) {
      setError("Las contraseñas no coinciden");
      return;
    }

    try {
      await signUp({ email, name, lastName, password });
    } catch (err: unknown) {
      const axiosErr = err as {
        response?: { data?: { detail?: string; message?: string } };
      };
      setError(
        axiosErr?.response?.data?.detail ||
          axiosErr?.response?.data?.message ||
          "Error al registrarse",
      );
    }
  };

  return (
    <form
      className={cn("flex flex-col gap-5", props.className)}
      onSubmit={handleSubmit}
      {...props}
    >
      {/* Brand logo - smaller size */}
      <div className="flex justify-center w-full mt-0">
        <div className="relative w-full max-w-[9rem] aspect-square">
          <img
            src={appLogo}
            alt="Logotipo"
            className="object-contain w-full h-full"
          />
        </div>
      </div>

      {/* Header Title */}
      <div className="flex flex-col items-center gap-1.5 text-center">
        <h1 className="font-poppins text-2xl font-bold text-brand-navy tracking-wide">
          Registro
        </h1>
        <p className="text-balance text-sm text-neutral-600 dark:text-neutral-300">
          Cree su cuenta para acceder a los servicios
        </p>
      </div>

      <div className="grid gap-5">
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
          <Label
            htmlFor="name"
            className="font-medium text-neutral-700 dark:text-neutral-200"
          >
            Nombre
          </Label>
          <Input
            id="name"
            type="text"
            placeholder="Su nombre"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="py-2.5"
          />
        </div>

        <div className="grid gap-2">
          <Label
            htmlFor="lastName"
            className="font-medium text-neutral-700 dark:text-neutral-200"
          >
            Apellidos
          </Label>
          <Input
            id="lastName"
            type="text"
            placeholder="Sus apellidos"
            required
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            className="py-2.5"
          />
        </div>

        <div className="grid gap-2">
          <Label
            htmlFor="password"
            className="font-medium text-neutral-700 dark:text-neutral-200"
          >
            Contraseña
          </Label>
          <Input
            id="password"
            type="password"
            placeholder="Mínimo 8 caracteres"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="py-2.5"
          />
        </div>

        <div className="grid gap-2">
          <Label
            htmlFor="confirmPassword"
            className="font-medium text-neutral-700 dark:text-neutral-200"
          >
            Confirmar contraseña
          </Label>
          <Input
            id="confirmPassword"
            type="password"
            placeholder="Repita su contraseña"
            required
            minLength={8}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="py-2.5"
          />
        </div>

        {error && <div className="text-red-500 text-sm">{error}</div>}

        <Button
          type="submit"
          className="w-full bg-brand-purple hover:bg-brand-purple-dark text-white font-medium mt-1 transition-colors"
          disabled={loading}
        >
          {loading ? "Registrando…" : "Registrarse"}
        </Button>
      </div>

      <div className="text-center text-sm mt-2">
        ¿Ya tiene cuenta?{" "}
        <Link
          to="/login"
          className="font-medium text-brand-navy hover:opacity-80 underline underline-offset-4 transition-colors"
        >
          Iniciar sesión
        </Link>
      </div>
    </form>
  );
}
