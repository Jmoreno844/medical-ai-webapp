"use client";

import {
  Card,
  // CardContent, // Not strictly needed if CardHeader contains everything
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"; // Assuming path is correct
import { Mic, ShieldCheck, UserCheck, Zap } from "lucide-react";

// Define feature data structure for easier mapping (optional but good practice)
const features = [
  {
    icon: Mic,
    title: "Accurate AI Transcription",
    description:
      "State-of-the-art speech recognition trained on medical terminology for high accuracy, even with accents and complex scenarios.",
    iconColor: "text-teal-600",
    bgColor: "bg-teal-100",
  },
  {
    icon: Zap,
    title: "Intelligent Document Generation",
    description:
      "Automatically create SOAP notes, clinical summaries, patient instructions, and customizable templates directly from transcripts.",
    iconColor: "text-teal-600", // You could vary colors slightly if desired
    bgColor: "bg-teal-100",
  },
  {
    icon: ShieldCheck,
    title: "HIPAA-Compliant Security",
    description:
      "Built with privacy at the core. End-to-end encryption and robust security protocols ensure patient data safety and compliance.",
    iconColor: "text-teal-600",
    bgColor: "bg-teal-100",
  },
  {
    icon: UserCheck,
    title: "Seamless Workflow Integration",
    description:
      "Easily export documents or integrate with leading EHR/EMR systems (coming soon/or specify if available) for a frictionless documentation process.",
    iconColor: "text-teal-600",
    bgColor: "bg-teal-100",
  },
];

export default function FeaturesSection() {
  return (
    <section id="features" className="w-full py-16 md:py-28 bg-gray-50">
      {" "}
      {/* Changed bg, increased padding */}
      <div className="container px-4 md:px-6 mx-auto">
        <div className="flex flex-col items-center justify-center space-y-4 text-center mb-12 md:mb-16">
          {" "}
          {/* Added margin-bottom */}
          <div className="space-y-3">
            {/* Optional: Add a small "Features" badge/pill */}
            {/* <div className="inline-block rounded-full bg-teal-100 px-3 py-1 text-sm font-medium text-teal-700">
              Core Features
            </div> */}
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl md:text-5xl text-gray-900">
              {" "}
              {/* Darker heading */}
              Streamline Your Practice with Intelligent Tools
            </h2>
            <p className="mx-auto max-w-3xl text-lg text-gray-600 md:text-xl">
              {" "}
              {/* Added subheading */}
              Leverage cutting-edge AI designed specifically for healthcare
              professionals to save time, reduce errors, and focus on patient
              care.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
          {" "}
          {/* Increased gap */}
          {features.map((feature) => {
            const Icon = feature.icon; // Assign component to variable starting with uppercase
            return (
              <Card
                key={feature.title}
                className="group bg-white rounded-xl shadow-sm border-2 border-transparent hover:shadow-lg hover:border-teal-500 hover:scale-[1.02] transition-all duration-300 ease-in-out flex flex-col" // Enhanced card styles & hover, added flex
              >
                <CardHeader className="flex-grow">
                  {" "}
                  {/* Added flex-grow to push content */}
                  <div
                    className={`flex items-center justify-center h-16 w-16 rounded-full bg-gradient-to-br from-teal-50 to-teal-200 mb-5 shadow-md group-hover:shadow-teal-200/50 group-hover:scale-110 transition-all duration-300`}
                  >
                    <Icon
                      className={`h-7 w-7 text-teal-600 group-hover:text-teal-700 transition-colors duration-300`}
                    />
                  </div>
                  <CardTitle className="text-lg font-semibold text-gray-800">
                    {" "}
                    {/* Adjusted title style */}
                    {feature.title}
                  </CardTitle>
                  <CardDescription className="text-gray-600 mt-1 leading-relaxed">
                    {" "}
                    {/* Adjusted description style */}
                    {feature.description}
                  </CardDescription>
                </CardHeader>
                {/* You could add CardContent here if needed later */}
                {/* <CardContent>
                    <p>Potentially more info or a button</p>
                </CardContent> */}
              </Card>
            );
          })}
        </div>
      </div>
    </section>
  );
}
