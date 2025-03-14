import sys
import traceback
import json


class DebugCorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Use print statement instead of logging
        print(
            "!!!!!!!!!! DebugCorsMiddleware initialized - CORS debugging active !!!!!!!!!!",
            flush=True,
        )
        sys.stdout.flush()

    def __call__(self, request):
        try:
            # Log detailed request information using print
            origin = request.headers.get("Origin", "No Origin")
            is_preflight = request.method == "OPTIONS"
            preflight_marker = "[PREFLIGHT]" if is_preflight else ""

            print(
                f"!!!!!!!!!! {preflight_marker} CORS Debug - Request: {request.method} {request.path} from {origin} !!!!!!!!!!",
                flush=True,
            )

            # Log all request headers for debugging
            headers_dict = dict(request.headers)
            print(
                f"!!!!!!!!!! Request headers: {json.dumps(headers_dict)} !!!!!!!!!!",
                flush=True,
            )

            response = self.get_response(request)

            # Log response details
            status_code = response.status_code
            cors_headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower().startswith("access-control") or "cors" in k.lower()
            }
            print(
                f"!!!!!!!!!! CORS response headers: {json.dumps(cors_headers)} !!!!!!!!!!",
                flush=True,
            )
            print(f"!!!!!!!!!! Response status: {status_code} !!!!!!!!!!", flush=True)

            # If this is a preflight request with an error status, add more debugging
            if is_preflight and status_code != 200:
                print(
                    "!!!!!!!!!! PREFLIGHT REQUEST FAILED - CORS issue detected! !!!!!!!!!!",
                    flush=True,
                )

            # Force flush stdout to ensure prints are visible
            sys.stdout.flush()
            return response
        except Exception as e:
            # Ensure any errors in the middleware itself are logged
            print(
                f"!!!!!!!!!! Exception in DebugCorsMiddleware: {str(e)} !!!!!!!!!!",
                flush=True,
            )
            print(f"!!!!!!!!!! {traceback.format_exc()} !!!!!!!!!!", flush=True)
            sys.stdout.flush()
            raise
