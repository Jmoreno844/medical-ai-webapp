import { AuthContext } from "@/commons/contexts/AuthContext";
import { useContext } from "react";
// Added imports for encounter creation
import { useEncountersSidebar } from "../app_layout/hooks/Encuentros/useEncountersSidebar";
import { useNavigationItems } from "../app_layout/hooks/useNavigationItems";
import { Link } from "react-router-dom";

// Mock data for recent transcript s
export default function HomePage() {
  const { userData } = useContext(AuthContext);
  const lastName = userData?.last_name || "";

  // Initialize hooks to get the "Crear Encuentro" functionality
  const { showRightSidebar, toggleSidebar } = useEncountersSidebar();
  const navigationItems = useNavigationItems(toggleSidebar, showRightSidebar);
  const crearEncuentroItem = navigationItems.find(
    (item) => item.icon === "/plus.svg" && item.action
  );

  return (
    <div className="h-screen bg-gray-50 text-gray-800 pt-6">
      {/* Main content container */}
      <div className="max-w-6xl mx-auto px-4 py-8 space-y-12">
        {/* Section 1: Welcome & Primary Action */}
        <section className="bg-white rounded-xl shadow-md p-8 relative">
          <div className="relative z-10">
            <h2 className="text-xl font-semibold text-gray-600">
              Bienvenido/a, Dr./Dra. {lastName}
            </h2>
            <h1 className="text-3xl md:text-4xl font-bold text-[#007A7A] mt-2 mb-4">
              Concéntrese en los pacientes, no en el papeleo
            </h1>
            <p className="text-lg text-gray-600 max-w-2xl mb-8">
              Registre o suba consultas, obtenga transcripciones precisas y genere
              notas clínicas en minutos.
            </p>
            <button
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                if (crearEncuentroItem?.action) {
                  crearEncuentroItem.action();
                }
              }}
              className="flex items-center bg-[#007A7A] hover:bg-[#006666] text-white py-3 px-6 rounded-lg font-semibold transition-all shadow-md hover:shadow-lg"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-5 w-5 mr-2"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v2H7a1 1 0 100 2h2v2a1 1 0 102 0v-2h2a1 1 0 100-2h-2V7z"
                  clipRule="evenodd"
                />
              </svg>
              Iniciar nueva consulta
            </button>
          </div>
        </section>

        {/* Section 2: How It Works */}
        <section className="bg-white rounded-xl shadow-md p-8">
          <h2 className="text-2xl font-bold text-center mb-10 text-gray-800">
            Cómo funciona
          </h2>

          <div className="grid md:grid-cols-3 gap-8">
            {/* Step 1 */}
            <div className="flex flex-col items-center text-center">
              <div className="bg-blue-50 p-4 rounded-full mb-4">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-10 w-10 text-[#4A90E2]"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
                  />
                </svg>
              </div>
              <h3 className="text-xl font-semibold mb-2 text-gray-800">
                Grabar o subir audio
              </h3>
              <p className="text-gray-600">
                Grabe audio de forma segura desde la app o suba un archivo de audio
                existente.
              </p>
            </div>

            {/* Step 2 */}
            <div className="flex flex-col items-center text-center">
              <div className="bg-blue-50 p-4 rounded-full mb-4">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-10 w-10 text-[#4A90E2]"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
              </div>
              <h3 className="text-xl font-semibold mb-2 text-gray-800">
                Transcribir y revisar
              </h3>
              <p className="text-gray-600">
                La IA transcribe la conversación con precisión. Revise y edite el
                texto cuando lo necesite.
              </p>
            </div>

            {/* Step 3 */}
            <div className="flex flex-col items-center text-center">
              <div className="bg-blue-50 p-4 rounded-full mb-4">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-10 w-10 text-[#4A90E2]"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
                  />
                </svg>
              </div>
              <h3 className="text-xl font-semibold mb-2 text-gray-800">
                Generar documentación
              </h3>
              <p className="text-gray-600">
                Genere al instante notas SOAP, resúmenes, interconsultas u otros
                formatos con plantillas personalizadas.
              </p>
            </div>
          </div>
        </section>

        {/* Section 4: Tips & Resources */}
        <section className="bg-white rounded-xl shadow-md p-8">
          <h2 className="text-2xl font-bold mb-6 text-gray-800">
            Consejos útiles
          </h2>

          <div className="grid md:grid-cols-2 gap-6">
            <div className="bg-blue-50 p-6 rounded-lg flex">
              <div className="mr-4 text-[#4A90E2]">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-8 w-8"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                  />
                </svg>
              </div>
              <div>
                <h3 className="font-semibold text-lg mb-2">Plantillas propias</h3>
                <p className="text-gray-600">
                  Puede crear plantillas de documentación con la estructura que
                  prefiera para ahorrar aún más tiempo.
                </p>
                <Link
                  to="/plantillas"
                  className="text-[#007A7A] font-medium inline-flex items-center mt-2 hover:underline"
                >
                  Ir a plantillas
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-4 w-4 ml-1"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10.293 5.293a1 1 0 011.414 0l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414-1.414L12.586 11H5a1 1 0 110-2h7.586l-2.293-2.293a1 1 0 010-1.414z"
                      clipRule="evenodd"
                    />
                  </svg>
                </Link>
              </div>
            </div>

            <div className="bg-blue-50 p-6 rounded-lg flex">
              <div className="mr-4 text-[#4A90E2]">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-8 w-8"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </div>
              <div>
                <h3 className="font-semibold text-lg mb-2">¿Necesita ayuda?</h3>
                <p className="text-gray-600">
                  Para mayor precisión, reduzca el ruido de fondo durante las
                  grabaciones.
                </p>
                <a
                  href="#"
                  className="text-[#007A7A] font-medium inline-flex items-center mt-2 hover:underline"
                >
                  Centro de ayuda
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-4 w-4 ml-1"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10.293 5.293a1 1 0 011.414 0l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414-1.414L12.586 11H5a1 1 0 110-2h7.586l-2.293-2.293a1 1 0 010-1.414z"
                      clipRule="evenodd"
                    />
                  </svg>
                </a>
              </div>
            </div>
          </div>
        </section>

        {/* Section 5: Security & Compliance Footer */}
        <section className="text-center p-4 border-t border-gray-200">
          <div className="flex justify-center items-center text-gray-500">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5 mr-2"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0017.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                clipRule="evenodd"
              />
            </svg>
            <span>
              Sus datos se protegen con cifrado. Diseñado pensando en estándares
              de cumplimiento clínico (p. ej. HIPAA).
            </span>
          </div>
          <div className="mt-2">
            <a
              href="#"
              className="text-sm text-gray-500 hover:text-gray-700 mx-2"
            >
              Política de privacidad
            </a>
            <a
              href="#"
              className="text-sm text-gray-500 hover:text-gray-700 mx-2"
            >
              Términos del servicio
            </a>
          </div>
        </section>
      </div>
    </div>
  );
}
