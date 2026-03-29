import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/commons/hooks/useAuth";
import { cn } from "@/lib/utils";
import { Button } from "@/commons/components/ui/button";
import { Input } from "@/commons/components/ui/input";
import { Label } from "@/commons/components/ui/label";

export function SignupForm(props: React.ComponentPropsWithoutRef<"form">) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [lastName, setLastName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const { signUp } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await signUp({ email, name, lastName, password });
      navigate("/home"); // redirect to home page after successful registration
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
    } catch (err: any) {
      setError(err?.response?.data?.message || "Registration error");
    }
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
          <img
            src="/brand_logo_no_text.png"
            alt="Brand Logo"
            className="object-contain w-full h-full"
          />
        </div>
      </div>

      {/* Header Title */}
      <div className="flex flex-col items-center gap-2 text-center">
        <h1 className="text-2xl font-bold text-main font-fun tracking-tight">
          Register
        </h1>
        <p className="text-balance text-sm text-neutral-600 dark:text-neutral-300">
          Create your account to access our services
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
            Name
          </Label>
          <Input
            id="name"
            type="text"
            placeholder="Your name"
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
            Last Name
          </Label>
          <Input
            id="lastName"
            type="text"
            placeholder="Your last name"
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
            Password
          </Label>
          <Input
            id="password"
            type="password"
            placeholder="Your password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="py-2.5"
          />
        </div>

        {error && <div className="text-red-500 text-sm">{error}</div>}

        <Button
          type="submit"
          className="w-full bg-main hover:bg-main_dark text-white font-medium py-6 mt-2 transition-colors"
        >
          Register
        </Button>
      </div>

      <div className="text-center text-sm mt-2">
        Already have an account?{" "}
        <Link
          to="/login"
          className="font-medium text-main hover:text-main_dark underline underline-offset-4 transition-colors"
        >
          Sign in
        </Link>
      </div>
    </form>
  );
}
