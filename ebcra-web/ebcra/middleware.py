import logging
import time

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class JWTMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = getattr(settings, "JWT_SERVICE_HOST", "")
        path = getattr(settings, "JWT_SERVICE_JS_PATH", "")

        if not host or not path:
            request.js_token = ""
        else:
            token = request.session.get("jwt_token")
            expires = request.session.get("jwt_expires", 0)

            if not token or time.time() > expires:
                url = host + path
                try:
                    resp = httpx.get(url, timeout=3.0)
                    resp.raise_for_status()
                    data = resp.json()
                    token = data.get("token", "")
                    request.session["jwt_token"] = token
                    request.session["jwt_expires"] = time.time() + 23 * 3600
                except httpx.HTTPStatusError as e:
                    logger.error("JWT service returned %s for %s", e.response.status_code, url)
                    token = ""
                except httpx.RequestError as e:
                    logger.error("JWT service call failed for %s: %s", url, e)
                    token = ""

            request.js_token = token

        return self.get_response(request)
