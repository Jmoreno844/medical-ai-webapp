function AboutPage() {
  return (
    <div className="flex flex-col items-center py-8">
      <h2 className="text-3xl font-bold mb-6">Acerca de esta aplicación</h2>
      <div className="bg-white p-6 rounded-lg shadow-md max-w-2xl">
        <p className="mb-4">
          Aplicación web médica desarrollada con React, Vite y React Router.
        </p>
        <p>
          Organización de rutas y componentes siguiendo buenas prácticas.
        </p>
      </div>
    </div>
  );
}

export default AboutPage;
