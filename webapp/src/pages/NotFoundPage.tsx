import { Link } from "react-router-dom";

function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center py-12">
      <h2 className="text-4xl font-bold text-red-500 mb-4">404</h2>
      <p className="text-xl mb-6">Página no encontrada</p>
      <p className="mb-8">
        La página que busca no existe o ha sido movida.
      </p>
      <Link
        to="/"
        className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
      >
        Volver al inicio
      </Link>
    </div>
  );
}

export default NotFoundPage;
