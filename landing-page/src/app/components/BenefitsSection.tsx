"use client";

import {
  CheckCircle2,
  Clock,
  Heart,
  ShieldCheck,
  Target,
  Zap,
} from "lucide-react";

export default function BenefitsSection() {
  return (
    <section className="w-full py-12 md:py-24 bg-slate-50">
      <div className="container mx-auto px-4 md:px-6">
        <div className="flex flex-col items-center justify-center space-y-4 text-center">
          <div className="space-y-2">
            <h2 className="text-3xl font-bold tracking-tighter sm:text-4xl md:text-5xl text-slate-800">
              Focus on Patients, Not Paperwork
            </h2>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 mt-12">
          <div className="flex items-start space-x-4">
            <div className="shrink-0">
              <Clock className="h-8 w-8 text-teal-500" />
            </div>
            <div>
              <h3 className="text-xl font-bold mb-2">Save Valuable Time</h3>
              <p className="text-slate-600">
                Reduce documentation time by up to 70%, giving you back hours in
                your day.
              </p>
            </div>
          </div>
          <div className="flex items-start space-x-4">
            <div className="shrink-0">
              <Target className="h-8 w-8 text-teal-500" />
            </div>
            <div>
              <h3 className="text-xl font-bold mb-2">Improve Note Accuracy</h3>
              <p className="text-slate-600">
                Minimize transcription errors with AI precision and medical
                terminology expertise.
              </p>
            </div>
          </div>
          <div className="flex items-start space-x-4">
            <div className="shrink-0">
              <CheckCircle2 className="h-8 w-8 text-teal-500" />
            </div>
            <div>
              <h3 className="text-xl font-bold mb-2">
                Reduce Clinician Burnout
              </h3>
              <p className="text-slate-600">
                Less administrative burden means more focus on care and
                professional satisfaction.
              </p>
            </div>
          </div>
          <div className="flex items-start space-x-4">
            <div className="shrink-0">
              <ShieldCheck className="h-8 w-8 text-teal-500" />
            </div>
            <div>
              <h3 className="text-xl font-bold mb-2">Ensure Compliance</h3>
              <p className="text-slate-600">
                Maintain secure, standardized records effortlessly with built-in
                compliance features.
              </p>
            </div>
          </div>
          <div className="flex items-start space-x-4">
            <div className="shrink-0">
              <Heart className="h-8 w-8 text-teal-500" />
            </div>
            <div>
              <h3 className="text-xl font-bold mb-2">
                Enhance Patient Experience
              </h3>
              <p className="text-slate-600">
                More face-time with patients, less screen-time during visits
                creates better relationships.
              </p>
            </div>
          </div>
          <div className="flex items-start space-x-4">
            <div className="shrink-0">
              <Zap className="h-8 w-8 text-teal-500" />
            </div>
            <div>
              <h3 className="text-xl font-bold mb-2">
                Boost Practice Efficiency
              </h3>
              <p className="text-slate-600">
                Streamline workflows and increase throughput without sacrificing
                quality or compliance.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
