function AboutPage() {
  return (
    <div className="flex flex-col items-center py-8">
      <h2 className="text-3xl font-bold mb-6">About This App</h2>
      <div className="bg-white p-6 rounded-lg shadow-md max-w-2xl">
        <p className="mb-4">
          This is a medical web application built with React, Vite, and React
          Router.
        </p>
        <p>
          The application follows best practices for routing and organization of
          components.
        </p>
      </div>
    </div>
  );
}

export default AboutPage;
