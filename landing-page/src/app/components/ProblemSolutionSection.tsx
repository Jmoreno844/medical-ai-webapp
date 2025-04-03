"use client";

import { Clock, Zap, CheckCircle, CornerDownRight } from "lucide-react";
import Image from "next/image";

export default function ProblemSolutionSection() {
  return (
    <section className="w-full py-16 md:py-28 bg-gray-50">
      <div className="container px-4 md:px-6 mx-auto">
        {/* Optional Section Header (Keep if desired) */}
        {/* <div className="text-center mb-12 md:mb-16">
          <h2 className="text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">From Burnout to Breakthrough</h2>
          <p className="mt-4 text-lg text-gray-600">See how AI transforms your documentation workflow.</p>
        </div> */}
        {/* Container for the two rows with vertical spacing */}
        <div className="space-y-16 md:space-y-24">
          {/* Row 1: Problem (Image Left, Text Right) */}
          <div className="grid gap-8 lg:grid-cols-2 lg:gap-12 items-center">
            {/* Image Column (Left on LG) */}
            <div className="relative aspect-video w-full overflow-hidden rounded-xl shadow-md">
              <Image
                src="/tired_real.png"
                alt="Medical professional looking stressed with paperwork"
                fill
                className="object-cover"
                sizes="(max-width: 1024px) 100vw, 50vw"
              />
            </div>
            {/* Text Column (Right on LG) */}
            <div className="space-y-4">
              <div className="inline-flex items-center rounded-lg bg-slate-100 p-3">
                <Clock className="h-7 w-7 text-slate-600" />
              </div>
              <h3 className="text-2xl md:text-3xl font-bold tracking-tight text-gray-800">
                The Documentation Drag
              </h3>
              <p className="text-gray-600 md:text-lg leading-relaxed">
                Manual documentation consumes valuable hours, leading to:
              </p>
              <ul className="space-y-2 text-gray-600">
                <li className="flex items-start">
                  <CornerDownRight className="h-5 w-5 mr-2 mt-1 text-slate-400 flex-shrink-0" />
                  <span>
                    Increased administrative burden & clinician burnout.
                  </span>
                </li>
                <li className="flex items-start">
                  <CornerDownRight className="h-5 w-5 mr-2 mt-1 text-slate-400 flex-shrink-0" />
                  <span>
                    Less time for direct patient interaction and care.
                  </span>
                </li>
                <li className="flex items-start">
                  <CornerDownRight className="h-5 w-5 mr-2 mt-1 text-slate-400 flex-shrink-0" />
                  <span>Potential for transcription errors and delays.</span>
                </li>
              </ul>
            </div>
          </div>

          {/* Row 2: Solution (Text Left, Image Right) */}
          <div className="grid gap-8 lg:grid-cols-2 lg:gap-12 items-center">
            {/* Text Column (Left on LG) */}
            <div className="space-y-4">
              <div className="inline-flex items-center rounded-lg bg-teal-100 p-3">
                <Zap className="h-7 w-7 text-teal-600" />
              </div>
              <h3 className="text-2xl md:text-3xl font-bold tracking-tight text-gray-900">
                Your AI-Powered Advantage
              </h3>
              <p className="text-gray-600 md:text-lg leading-relaxed">
                MedScribe AI streamlines your workflow with:
              </p>
              <ul className="space-y-2 text-gray-600">
                <li className="flex items-start">
                  <CheckCircle className="h-5 w-5 mr-2 mt-1 text-teal-500 flex-shrink-0" />
                  <span>
                    <b>Instant & Accurate Transcription:</b> Captures
                    multi-speaker dialogue with high medical term accuracy.
                  </span>
                </li>
                <li className="flex items-start">
                  <CheckCircle className="h-5 w-5 mr-2 mt-1 text-teal-500 flex-shrink-0" />
                  <span>
                    <b>Automated Note Generation:</b> Creates customizable SOAP
                    notes, summaries, letters, and more in minutes.
                  </span>
                </li>
                <li className="flex items-start">
                  <CheckCircle className="h-5 w-5 mr-2 mt-1 text-teal-500 flex-shrink-0" />
                  <span>
                    <b>Time Savings & Reduced Burnout:</b> Frees up hours daily
                    to focus on what matters most – your patients.
                  </span>
                </li>
              </ul>
            </div>
            {/* Image Column (Right on LG) */}
            <div className="relative aspect-video w-full overflow-hidden rounded-xl shadow-md">
              <Image
                src="/free_real.png"
                alt="Clean AI interface showing efficient medical documentation"
                fill
                className="object-cover"
                sizes="(max-width: 1024px) 100vw, 50vw"
              />
            </div>
          </div>
        </div>{" "}
        {/* End of space-y container */}
      </div>
    </section>
  );
}
