"use client";

import { useEffect, useRef, useState } from "react";

type RevealProps = {
  children: React.ReactNode;
  className?: string;
  /** Delay in ms before the animation starts once in view. */
  delay?: number;
};

export default function Reveal({ children, className, delay = 0 }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      // Fire once the element is well into the viewport (not just its top edge):
      // the negative bottom margin shrinks the trigger area up from the bottom.
      { threshold: 0, rootMargin: "0px 0px -25% 0px" },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      style={{ transitionDelay: `${delay}ms` }}
      className={`transition-all duration-700 ease-out motion-reduce:transition-none ${
        visible ? "translate-y-0 opacity-100" : "translate-y-6 opacity-0"
      } ${className ?? ""}`}
    >
      {children}
    </div>
  );
}
