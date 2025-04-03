import EncuentroHeader from "../encuentroHeader/EncuentroHeader";

export default function EncuentroPage() {
  return (
    <div className="flex flex-col h-screen">
      <EncuentroHeader />
      {/* Add list of encounters here if needed */}
      <div className="flex-1 p-4">
        <h2 className="text-xl font-semibold mb-4">Mis Encuentros</h2>
        {/* Encounter list could go here */}
      </div>
    </div>
  );
}
