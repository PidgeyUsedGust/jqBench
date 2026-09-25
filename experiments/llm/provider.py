"""Small non-streaming OpenRouter transport."""

import json
import os
import time
import urllib.error
import urllib.request


class ProviderError(RuntimeError):
    pass


class RateLimitError(ProviderError):
    pass


def complete(request, *, timeout=120, attempts=3):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ProviderError(
            "Cache miss: set OPENROUTER_API_KEY to enable paid OpenRouter requests"
        )
    for attempt in range(attempts):
        call = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(request).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(call, timeout=timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            # Do not echo headers, credentials, or potentially sensitive request bodies.
            if error.code in {429, 502, 503, 504} and attempt + 1 < attempts:
                time.sleep(2**attempt)
                continue
            cls = RateLimitError if error.code == 429 else ProviderError
            raise cls(f"OpenRouter HTTP {error.code} for {request['model']}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            # Ambiguous network failures are not retried: the request might be billed.
            raise ProviderError(
                f"OpenRouter connection failed for {request['model']}: {type(error).__name__}"
            ) from error
        except (ValueError, UnicodeError) as error:
            raise ProviderError("OpenRouter returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise ProviderError("OpenRouter returned a non-object response")
        if "error" in payload:
            error = payload["error"]
            code = (
                error.get("code", "unknown") if isinstance(error, dict) else "unknown"
            )
            raise ProviderError(
                f"OpenRouter provider error {code} for {request['model']}"
            )
        return payload
    raise ProviderError("OpenRouter retry budget exhausted")
