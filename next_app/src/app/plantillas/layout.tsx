import { Metadata } from "next";
import BaseLayout from "../app_layout/layout";

export const metadata: Metadata = {
    title: "Plantillas Médicas",
    description: "Módulo de gestión de plantillas médicas",
};

export default function PlantillasLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return <BaseLayout metadata={metadata}>{children}</BaseLayout>;
}
