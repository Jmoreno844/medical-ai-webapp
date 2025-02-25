"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function LoginForm(props: React.ComponentPropsWithoutRef<"form">) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { login, error, loading } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      console.log('Attempting login...'); // Debug log
      await login({ email, password });
      router.push("/home");
    } catch (err) {
      console.error('Login error:', err); // Debug log
    }
  };

  const handleRedirect = (path: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    router.push(path);
  };

  return (
    <form
      className={cn("flex flex-col gap-6", props.className)}
      onSubmit={handleSubmit}
      {...props}
    >
      {/* Brand logo */}
      <div className="flex justify-center">
        <Image
          src="/brand_logo.svg"
          alt="Brand Logo"
          width={150}
          height={150}
          className="object-contain"
        />
      </div>
      <div className="flex flex-col items-center gap-2 text-center">
        <h1 className="text-2xl font-bold text-main">Bienvenido</h1>
        <p className="text-balance text-sm text-neutral-500 dark:text-neutral-400">
          Ingresa con tus credenciales
        </p>
      </div>
      <div className="grid gap-6">
        {error && (
          <div className="p-3 text-sm text-red-500 bg-red-50 rounded-md">
            {error}
          </div>
        )}
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
            <Label htmlFor="password">Password</Label>
            <a
              href="#"
              onClick={handleRedirect("/forgot-password")}
              className="ml-auto text-sm underline-offset-4 hover:underline"
            >
              Olvidates tu contraseña?
            </a>
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
          className="w-full bg-main hover:bg-main_dark"
          disabled={loading}
        >
          {loading ? 'Iniciando sesión...' : 'Login'}
        </Button>
      </div>
      <div className="text-center text-sm">
        No tienes una cuenta?{" "}
        <a
          href="#"
          onClick={handleRedirect("/registro")}
          className="underline underline-offset-4"
        >
          Registrate
        </a>
      </div>
    </form>
  );
}
