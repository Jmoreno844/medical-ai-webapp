import { SignupForm } from "./components/SignupForm";

export default function RegistroPage() {
  return (
    <div className="grid min-h-svh lg:grid-cols-2 gap-6 p-4 md:p-6">
      <div className="flex flex-col pt-3 pb-6 px-6 md:pt-4 md:pb-8 md:px-8 rounded-xl bg-white dark:bg-neutral-900">
        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-[21rem] mx-auto">
            <SignupForm />
          </div>
        </div>
      </div>
      <div className="relative hidden bg-neutral-100 lg:block dark:bg-neutral-800 rounded-xl overflow-hidden h-full">
        <img
          src="/hero_image.jpeg"
          alt="Servicios médicos"
          className="object-cover absolute inset-0 w-full h-full dark:brightness-[0.3] dark:grayscale"
        />
        <div className="absolute inset-0 bg-main/10 dark:bg-main_dark/20"></div>
      </div>
    </div>
  );
}
