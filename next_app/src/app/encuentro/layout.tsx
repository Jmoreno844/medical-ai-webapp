import { Metadata } from "next";
import BaseLayout from "../app_layout/layout";

export const metadata: Metadata = {
  title: "Medical Transcription Session",
  description: "Medical transcription session module",
};

export default function SessionLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <BaseLayout metadata={metadata}>{children}</BaseLayout>;
}
