"use client";

import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";
import Link from "next/link"; // Import the Link component

export default function CtaSection() {
  return (
    <section className="w-full py-16 md:py-28 bg-gradient-to-br from-slate-800 to-slate-900 text-white">
      {" "}
      {/* Keeping the dark, impactful background */}
      <div className="container px-4 md:px-6 mx-auto">
        <div className="flex flex-col items-center justify-center space-y-6 md:space-y-8 text-center">
          {" "}
          {/* Adjusted spacing */}
          <div className="space-y-3 md:space-y-4">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl md:text-5xl lg:text-6xl text-slate-100">
              See the Difference AI Can Make
            </h2>
            <p className="mx-auto max-w-[750px] text-slate-300 md:text-xl leading-relaxed">
              Experience firsthand how MedScribe AI transforms conversations
              into accurate documentation in minutes.
            </p>
          </div>
          <div className="w-full max-w-sm pt-4 md:pt-6">
            {" "}
            {/* Adjusted top padding */}
            {/* Link wrapping the Button */}
            <Link href="https://medapp.sebastianmoreno.lat" legacyBehavior>
              {/* ===> REPLACE "/demo" with your actual link destination <=== */}
              <a className="block">
                {" "}
                {/* Anchor tag needed for legacyBehavior */}
                <Button
                  size="lg"
                  className="w-full bg-teal-600 hover:bg-teal-700 text-white font-semibold shadow-lg transition duration-300 ease-in-out transform hover:scale-105 px-8 py-4" // Kept prominent style
                >
                  Try It Yourself
                  <ArrowRight className="ml-2 h-5 w-5" />
                </Button>
              </a>
            </Link>
            {/* Removed the "No credit card required..." text */}
          </div>
          {/* Email Input and Request Demo button section remains removed */}
        </div>
      </div>
    </section>
  );
}

// Note: Using legacyBehavior and an inner <a> tag with Link is often
// required when wrapping custom components like Shadcn's Button
// to ensure proper hyperlink functionality and styling.
// If your setup works without legacyBehavior, you can remove it and the <a> tag.
