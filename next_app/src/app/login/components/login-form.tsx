"use client";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useState } from "react";
import { useAuth } from "../hooks/useAuth";

export function LoginForm({
  className,
  ...props
}: React.ComponentPropsWithoutRef<"div">) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { login, forgotPassword, loading, error } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await login({ email, password });
      // Redirect or handle successful login
    } catch (err) {
      // Error is handled by the hook
    }
  };

  const handleForgotPassword = async () => {
    if (!email) {
      alert("Por favor ingresa tu email primero");
      return;
    }
    try {
      await forgotPassword(email);
      alert(
        "Si el email existe, recibirás instrucciones para resetear tu contraseña"
      );
    } catch (err) {
      // Error is handled by the hook
    }
  };

  return (
    <div className={cn("flex flex-col gap-6", className)} {...props}>
      <Card>
        <CardHeader className="text-center pb-4">
          <CardTitle className="text-3xl text-blue-500 font-fun tracking-wide">
            MedAssist IA
          </CardTitle>
          <CardDescription className="pt-2">Bienvenido</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-6" onSubmit={handleSubmit}>
            {error && (
              <div className="text-sm text-red-500 text-center">{error}</div>
            )}
            <div className="grid gap-2">
              <div className="grid gap-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="m@example.com"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <div className="flex items-center">
                  <Label htmlFor="password">Contraseña</Label>
                  <button
                    type="button"
                    onClick={handleForgotPassword}
                    className="ml-auto text-sm underline-offset-4 hover:underline"
                  >
                    Olvidaste tu contraseña?
                  </button>
                </div>
                <Input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <Button
                type="submit"
                className="w-full bg-blue-500 hover:bg-blue-600 font-semibold"
                disabled={loading}
              >
                {loading ? "Cargando..." : "Entrar"}
              </Button>
            </div>
            <div className="text-center text-sm">
              No tienes una cuenta?{" "}
              <a href="#" className="underline underline-offset-4">
                Registrate
              </a>
            </div>
          </form>
        </CardContent>
      </Card>
      <div className="text-balance text-center text-xs text-muted-foreground [&_a]:underline [&_a]:underline-offset-4 [&_a]:hover:text-primary  ">
        Al dar click en continuar, concuerdas con nuestros{" "}
        <a href="#">Terminos de Servicio</a> &{" "}
        <a href="#">Politica de Privacidad</a>.
      </div>
    </div>
  );
}
