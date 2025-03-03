import React from "react";
import { EncounterDetailClient } from "./EncounterDetailClient";

// Server component that properly handles params
export default async function EncounterDetailPage({
  params,
}: {
  params: { id: string };
}) {
  // Await params to get the id
  const id = await Promise.resolve(params).then((p) => p.id);

  // Pass the unwrapped ID to the client component
  return <EncounterDetailClient id={id} />;
}
