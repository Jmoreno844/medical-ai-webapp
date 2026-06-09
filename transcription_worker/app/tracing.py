from worker_runtime.tracing import configure_tracing as _configure_tracing


def configure_tracing(app, settings, *, service_name: str) -> None:
    _configure_tracing(app, settings, service_name=service_name)
