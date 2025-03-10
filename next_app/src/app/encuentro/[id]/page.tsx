import React from "react";
import { EncounterDetailClient } from "./EncounterDetailClient";

// Define the proper type for Params in Next.js 15+
type Params = Promise<{ id: string }>;

export default async function EncounterDetailPage(props: { params: Params }) {
    // Await the params Promise to get the id
    const params = await props.params;
    const id = params.id;

    // Pass the ID to the client component
    return <EncounterDetailClient id={id} />;
}
