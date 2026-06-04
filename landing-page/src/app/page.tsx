import Navbar from "./components/Navbar";
import HeroSection from "./components/HeroSection";
import ProblemSection from "./components/ProblemSection";
import HowItWorksSection from "./components/HowItWorksSection";

export default function Home() {
  return (
    <main className="min-h-screen bg-slate-50">
      <Navbar />
      <div id="home">
        <HeroSection />
      </div>
      <div id="problema">
        <ProblemSection />
      </div>
      <div id="como-funciona">
        <HowItWorksSection />
      </div>
    </main>
  );
}
