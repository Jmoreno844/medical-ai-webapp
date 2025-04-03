"use client";

import Navbar from "./components/Navbar";
import HeroSection from "./components/HeroSection";
import ProblemSolutionSection from "./components/ProblemSolutionSection";
import FeaturesSection from "./components/FeaturesSection";
import HowItWorksSection from "./components/HowItWorksSection";
import BenefitsSection from "./components/BenefitsSection";
import SecuritySection from "./components/SecuritySection";
import CtaSection from "./components/CtaSection";
import Footer from "./components/Footer";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      <main>
        <div id="home">
          <HeroSection />
        </div>
        <ProblemSolutionSection />
        <div id="features">
          <FeaturesSection />
        </div>
        <div id="how-it-works">
          <HowItWorksSection />
        </div>
        <BenefitsSection />
        <div id="security">
          <SecuritySection />
        </div>
        <div id="pricing">
          <CtaSection />
        </div>
      </main>
      <div id="contact">
        <Footer />
      </div>
    </div>
  );
}
