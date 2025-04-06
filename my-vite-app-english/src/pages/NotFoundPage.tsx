import { Link } from "react-router-dom";

function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center py-12">
      <h2 className="text-4xl font-bold text-red-500 mb-4">404</h2>
      <p className="text-xl mb-6">Page Not Found</p>
      <p className="mb-8">
        The page you are looking for doesn't exist or has been moved.
      </p>
      <Link
        to="/"
        className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
      >
        Go back to home
      </Link>
    </div>
  );
}

export default NotFoundPage;
