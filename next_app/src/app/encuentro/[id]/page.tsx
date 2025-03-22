import React from "react";
import { EncounterDetailClient } from "./EncounterDetailClient";

// Define the proper type for Params in Next.js
type Params = {
    id: string;
};

// Make the page component async to handle Next.js dynamic params
export default async function EncounterDetailPage({
    params,
}: {
    params: Params | Promise<Params>;
}) {
    // Await the params if it's a promise
    const resolvedParams = await Promise.resolve(params);

    // Now we can safely access the id
    const id = resolvedParams.id;

    // Pass the ID to the client component
    return <EncounterDetailClient id={id} />;
}
