"use client";

import { CheckCircle2, Lock, ShieldCheck } from "lucide-react";

export default function SecuritySection() {
  return (
    <section id="security" className="w-full py-12 md:py-24 bg-white">
      <div className="container mx-auto px-4 md:px-6">
        <div className="flex flex-col items-center justify-center space-y-4 text-center max-w-3xl mx-auto">
          <div className="space-y-2">
            <Lock className="h-12 w-12 text-teal-500 mx-auto mb-4" />
            <h2 className="text-3xl font-bold tracking-tighter sm:text-4xl text-slate-800">
              Your Data Security is Our Priority
            </h2>
            <p className="text-slate-600 md:text-lg">
              MedScribe AI is built with security at its core. We are fully
              HIPAA compliant, employing end-to-end encryption, secure data
              storage, access controls, and regular audits to protect sensitive
              patient health information (PHI).
            </p>
          </div>
          <div className="flex flex-wrap justify-center gap-4 mt-6">
            <div className="flex items-center space-x-2 bg-slate-100 rounded-full px-4 py-2">
              <ShieldCheck className="h-5 w-5 text-teal-500" />
              <span className="text-sm font-medium">HIPAA Compliant</span>
            </div>
            <div className="flex items-center space-x-2 bg-slate-100 rounded-full px-4 py-2">
              <Lock className="h-5 w-5 text-teal-500" />
              <span className="text-sm font-medium">End-to-End Encryption</span>
            </div>
            <div className="flex items-center space-x-2 bg-slate-100 rounded-full px-4 py-2">
              <CheckCircle2 className="h-5 w-5 text-teal-500" />
              <span className="text-sm font-medium">Secure Cloud Storage</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
