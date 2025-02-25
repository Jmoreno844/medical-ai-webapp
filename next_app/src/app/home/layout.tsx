import { Metadata } from "next";
import BaseLayout from "../app_layout/layout";

export const metadata: Metadata = {
  title: "Home - Medical Web App",
  description: "Medical Web App Home Page",
};

export default function HomeLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <BaseLayout metadata={metadata}>{children}</BaseLayout>;
}
