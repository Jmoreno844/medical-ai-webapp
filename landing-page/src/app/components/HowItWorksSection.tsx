"use client";

import { BrainCircuit, FileText, Mic } from "lucide-react"; // Import relevant icons

// Define steps data (optional but good practice)
const steps = [
  {
    number: "1",
    title: "Record or Upload Audio",
    description:
      "Securely upload existing audio/video recordings or use our integrated recorder during patient encounters.",
    iconColor: "text-white", // Changed to white for better contrast
    bgColor: "bg-teal-600", // Changed to darker teal for better contrast with white icon
  },
  {
    number: "2",
    title: "Intelligent AI Processing",
    description:
      "Our specialized AI accurately transcribes the conversation, identifies speakers, and extracts key medical information.",
    iconColor: "text-white", // Changed to white for better contrast
    bgColor: "bg-teal-600", // Changed to darker teal for better contrast with white icon
  },
  {
    number: "3",
    title: "Review & Export Document",
    description:
      "Receive an accurate transcript and structured clinical note. Review, edit if necessary, and export seamlessly.",
    iconColor: "text-white", // Changed to white for better contrast
    bgColor: "bg-teal-600", // Changed to darker teal for better contrast with white icon
  },
];

export default function HowItWorksSection() {
  return (
    <section id="how-it-works" className="w-full py-16 md:py-28 bg-white">
      {" "}
      {/* Consistent padding */}
      <div className="container px-4 md:px-6 mx-auto">
        <div className="flex flex-col items-center justify-center space-y-4 text-center mb-16 md:mb-20">
          {" "}
          {/* Increased margin-bottom */}
          <div className="space-y-3">
            {/* Optional: Add a small badge/pill */}
            {/* <div className="inline-block rounded-full bg-gray-100 px-3 py-1 text-sm font-medium text-gray-700">
              Simple Process
            </div> */}
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl md:text-5xl text-gray-900">
              How Our AI Assistant Works
            </h2>
            <p className="mx-auto max-w-2xl text-lg text-gray-600 md:text-xl">
              Transform conversations into accurate documentation in three
              simple steps.
            </p>
          </div>
        </div>

        {/* Removed the absolute positioned line */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-12 md:gap-16">
          {" "}
          {/* Increased gap */}
          {steps.map((step, index) => {
            return (
              <div
                key={step.title}
                className="flex flex-col items-center text-center space-y-4"
              >
                {" "}
                {/* Adjusted spacing */}
                {/* Step Number */}
                <div className="text-3xl font-bold text-teal-600 mb-2">
                  {" "}
                  {/* Prominent Step Number */}
                  {step.number}
                </div>
                {/* Icon */}
                <div
                  className={`flex items-center justify-center w-20 h-20 rounded-full ${step.bgColor} mb-4 shadow-sm`}
                >
                  {" "}
                  {/* Styled Icon Container */}
                  {index === 0 && (
                    <Mic className={`w-10 h-10 ${step.iconColor}`} />
                  )}
                  {index === 1 && (
                    <BrainCircuit className={`w-10 h-10 ${step.iconColor}`} />
                  )}
                  {index === 2 && (
                    <FileText className={`w-10 h-10 ${step.iconColor}`} />
                  )}
                </div>
                {/* Title */}
                <h3 className="text-xl font-semibold text-gray-800 pt-2">
                  {" "}
                  {/* Added padding-top */}
                  {step.title}
                </h3>
                {/* Description */}
                <p className="text-gray-600 leading-relaxed">
                  {step.description}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
