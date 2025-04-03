"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Mic } from "lucide-react";
import Image from "next/image";

export default function Navbar() {
  const [activeSection, setActiveSection] = useState("home");
  const sections = ["home", "features", "how-it-works", "contact"];

  // Function to scroll to a section with custom offsets
  const scrollToSection = (id: string) => {
    const element = document.getElementById(id);
    if (!element) return;

    // Get element position relative to the viewport
    const rect = element.getBoundingClientRect();

    // Calculate current scroll position
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;

    // Define offsets for specific sections (adjust these values as needed)
    const offsets = {
      home: -80, // Scroll all the way to top for home
      features: -100, // Scroll to features minus 100px offset
      "how-it-works": -120,
      contact: -80,
    };

    // Calculate target position with offset
    const targetPosition =
      rect.top + scrollTop + (offsets[id as keyof typeof offsets] || 0);

    // Smooth scroll to target position
    window.scrollTo({
      top: targetPosition,
      behavior: "smooth",
    });

    setActiveSection(id);
  };

  // Function to determine which section is currently in view
  useEffect(() => {
    const handleScroll = () => {
      // Add a small buffer to prioritize sections at the top
      const scrollPosition = window.scrollY + 150;

      // Find the section that's currently in view
      let currentSection = sections[0];

      for (const section of sections) {
        const element = document.getElementById(section);
        if (!element) continue;

        // If the top of the section is above our current scroll position,
        // this is the active section
        if (element.offsetTop <= scrollPosition) {
          currentSection = section;
        }
      }

      if (currentSection !== activeSection) {
        setActiveSection(currentSection);
      }
    };

    // Throttle scroll events for better performance
    let isScrolling = false;
    window.addEventListener("scroll", () => {
      if (!isScrolling) {
        window.requestAnimationFrame(() => {
          handleScroll();
          isScrolling = false;
        });
        isScrolling = true;
      }
    });

    // Initial check on mount
    handleScroll();

    return () => {
      window.removeEventListener("scroll", handleScroll);
    };
  }, [activeSection, sections]);

  return (
    <header className="sticky top-0 z-40 w-full border-b bg-white/80 backdrop-blur-sm">
      <div className="px-12 flex h-16 items-center justify-between  md:px-6 w-full ">
        <div className="flex items-center gap-2 font-bold text-slate-700">
          <Image
            src="/brand_logo.svg"
            alt="MedScribe Logo"
            width={30}
            height={30}
            className="mr-2"
          />
          <span className=" text-2xl font-bold">MedScribe AI</span>
        </div>
        <nav className="hidden md:flex items-center gap-6 text-base mx-auto">
          {sections.map((section) => (
            <button
              key={section}
              onClick={() => scrollToSection(section)}
              className={`relative font-medium transition-all duration-300 ${
                activeSection === section
                  ? "text-teal-500 font-medium"
                  : "text-slate-700 hover:text-teal-500"
              }`}
            >
              {section
                .split("-")
                .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
                .join(" ")}
              <span
                className={`absolute bottom-0 left-0 h-0.5 bg-teal-500 transition-all duration-300 ${
                  activeSection === section ? "w-full" : "w-0"
                }`}
              ></span>
            </button>
          ))}
        </nav>
        <div>
          <Button className="bg-teal-500 hover:bg-teal-600 text-base font-semibold ml-28">
            Try it
          </Button>
        </div>
      </div>
    </header>
  );
}
