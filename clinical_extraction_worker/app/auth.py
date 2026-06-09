from worker_runtime.auth import verify_cloud_tasks_request as _verify_cloud_tasks_request


def verify_cloud_tasks_request(request, settings) -> None:
    _verify_cloud_tasks_request(request, settings)
