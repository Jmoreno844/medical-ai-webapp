import { useState } from "react";

function HomePage() {
  const [count, setCount] = useState(0);

  return (
    <div className="flex flex-col items-center py-8">
      <h2 className="text-3xl font-bold mb-6">
        Welcome to the Medical Web App
      </h2>
      <div className="bg-white p-6 rounded-lg shadow-md">
        <button
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          onClick={() => setCount((count) => count + 1)}
        >
          Count is {count}
        </button>
        <p className="mt-4">
          This is the home page of your medical application.
        </p>
      </div>
    </div>
  );
}

export default HomePage;
