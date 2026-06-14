from worker_runtime.logging import configure_logging as _configure_logging


def configure_logging(settings, *, service_name: str) -> None:
    _configure_logging(settings, service_name=service_name)
