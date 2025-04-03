"use client";

import { Button } from "@/components/ui/button";
import { ArrowRight, PlayCircle } from "lucide-react";
import { useEffect, useState } from "react";

export default function HeroSection() {
  // Dynamically calculate viewport height to handle mobile browsers better
  const [viewportHeight, setViewportHeight] = useState("100vh");

  useEffect(() => {
    // Update viewport height on resize
    const updateViewportHeight = () => {
      setViewportHeight(`${window.innerHeight}px`);
    };

    // Set initial height
    updateViewportHeight();

    // Add resize listener
    window.addEventListener("resize", updateViewportHeight);

    // Clean up
    return () => window.removeEventListener("resize", updateViewportHeight);
  }, []);

  return (
    <section
      className="w-full relative overflow-hidden bg-gray-50 flex items-center"
      style={{
        minHeight: `calc(${viewportHeight} - var(--navbar-height, 64px))`,
        height: `calc(${viewportHeight} - var(--navbar-height, 64px))`,
      }}
    >
      {/* Abstract Shapes Background */}
      <div className="absolute inset-0 -z-0 opacity-70">
        <div className="absolute top-0 -left-1/4 w-72 h-72 md:w-96 md:h-96 bg-blue-400 rounded-full filter blur-3xl opacity-70 animate-blob animation-delay-2000"></div>
        <div className="absolute top-0 -right-1/4 w-72 h-72 md:w-96 md:h-96 bg-teal-400 rounded-full filter blur-3xl opacity-70 animate-blob animation-delay-4000"></div>
        <div className="absolute -bottom-8 left-1/3 w-72 h-72 md:w-96 md:h-96 bg-purple-300 rounded-full filter blur-3xl opacity-60 animate-blob animation-delay-6000"></div>
      </div>

      <div className="container px-4 md:px-6 relative z-10 mx-auto py-8 md:py-10">
        <div className="flex flex-col items-center justify-center space-y-6 md:space-y-8 text-center">
          <div className="space-y-3 md:space-y-4">
            <h1 className="text-4xl font-bold tracking-tighter sm:text-5xl md:text-6xl lg:text-7xl text-gray-900">
              Focus on Patients, <br className="hidden sm:inline" />
              Not Paperwork.
            </h1>
            <p className="mx-auto max-w-[750px] text-gray-600 md:text-xl leading-relaxed">
              MedScribe AI instantly transforms medical conversations into
              accurate, structured clinical documentation using advanced AI.
              Reclaim your time.
            </p>
          </div>
          <div className="flex flex-col items-center sm:flex-row gap-4">
            <Button
              size="lg"
              className="bg-teal-600 hover:bg-teal-700 text-white font-semibold px-6 py-3"
            >
              Start Your Free Trial
              <ArrowRight className="ml-2 h-5 w-5" />
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="border-gray-300 text-gray-700 hover:bg-gray-100 font-medium px-6 py-3"
            >
              <PlayCircle className="mr-2 h-5 w-5 text-teal-500" />
              Watch Demo
            </Button>
          </div>
          <p className="text-sm text-gray-500 pt-4">
            HIPAA Compliant • Secure • Trusted by Healthcare Professionals
          </p>
        </div>
      </div>
    </section>
  );
}
