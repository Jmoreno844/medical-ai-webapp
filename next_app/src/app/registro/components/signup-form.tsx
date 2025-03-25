"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import Image from "next/image";

export function SignupForm(props: React.ComponentPropsWithoutRef<"form">) {
    const [email, setEmail] = useState("");
    const [name, setName] = useState("");
    const [lastName, setLastName] = useState("");
    const [password, setPassword] = useState("");
    const { signUp } = useAuth();
    const router = useRouter();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await signUp({ email, name, lastName, password });
            router.push("/login?success=true"); // redirect with success flag
            // On successful signup, redirect as needed
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
        } catch (err) {
            // Handle error (optional)
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
            {/* Brand logo - smaller size */}
            <div className="flex justify-center w-full mt-0">
                <div className="relative w-full max-w-[200px] aspect-square">
                    <Image
                        src="/brand_logo_no_text.png"
                        alt="Brand Logo"
                        fill
                        sizes="(max-width: 768px) 150px, 200px"
                        priority
                        className="object-contain"
                    />
                </div>
            </div>

            {/* Header Title */}
            <div className="flex flex-col items-center gap-2 text-center">
                <h1 className="text-2xl font-bold text-main font-fun tracking-tight">
                    Registro
                </h1>
                <p className="text-balance text-sm text-neutral-600 dark:text-neutral-300">
                    Crea tu cuenta para acceder a nuestros servicios médicos
                </p>
            </div>

            <div className="grid gap-7">
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
                    <Label
                        htmlFor="name"
                        className="font-medium text-neutral-700 dark:text-neutral-200"
                    >
                        Nombre
                    </Label>
                    <Input
                        id="name"
                        type="text"
                        placeholder="Tu nombre"
                        required
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        className="py-2.5"
                    />
                </div>

                <div className="grid gap-2.5">
                    <Label
                        htmlFor="lastName"
                        className="font-medium text-neutral-700 dark:text-neutral-200"
                    >
                        Apellido
                    </Label>
                    <Input
                        id="lastName"
                        type="text"
                        placeholder="Tu apellido"
                        required
                        value={lastName}
                        onChange={(e) => setLastName(e.target.value)}
                        className="py-2.5"
                    />
                </div>

                <div className="grid gap-2.5">
                    <Label
                        htmlFor="password"
                        className="font-medium text-neutral-700 dark:text-neutral-200"
                    >
                        Contraseña
                    </Label>
                    <Input
                        id="password"
                        type="password"
                        placeholder="Tu contraseña"
                        required
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className="py-2.5"
                    />
                </div>

                <Button
                    type="submit"
                    className="w-full bg-main hover:bg-main_dark text-white font-medium py-6 mt-2 transition-colors"
                >
                    Registrarse
                </Button>
            </div>

            <div className="text-center text-sm mt-2">
                ¿Ya tienes una cuenta?{" "}
                <a
                    href="#"
                    onClick={handleRedirect("/login")}
                    className="font-medium text-main hover:text-main_dark underline underline-offset-4 transition-colors"
                >
                    Iniciar sesión
                </a>
            </div>
        </form>
    );
}
