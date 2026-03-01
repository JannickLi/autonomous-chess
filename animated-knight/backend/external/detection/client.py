"""HTTP client for the real detection API.

This is a placeholder for when the real detection API is available.
Implement HttpDetectionClient here following the DetectionClient interface.

Example implementation:

```python
import httpx
from backend.external.interfaces import DetectionClient, DetectionResult


class HttpDetectionClient(DetectionClient):
    def __init__(self, base_url: str, timeout: float = 10.0):
        self._base_url = base_url.rstrip('/')
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def capture(self) -> DetectionResult:
        try:
            response = await self._client.post(f"{self._base_url}/capture")
            response.raise_for_status()
            data = response.json()
            return DetectionResult(
                success=True,
                fen=data.get("fen"),
                pieces=data.get("pieces"),
            )
        except Exception as e:
            return DetectionResult(
                success=False,
                error=str(e),
            )

    async def health_check(self) -> bool:
        try:
            response = await self._client.get(f"{self._base_url}/health")
            return response.status_code == 200
        except Exception:
            return False
```
"""
