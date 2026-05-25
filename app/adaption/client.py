from pathlib import Path
from typing import Any

import httpx


class AdaptionClientError(RuntimeError):
    pass


class AdaptionClient:
    def __init__(self, *, api_key: str, base_url: str, http_client: httpx.AsyncClient | None = None) -> None:
        if not api_key:
            raise AdaptionClientError("Adaption API key is required")
        if not base_url:
            raise AdaptionClientError("Adaption base URL is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._http_client = http_client

    async def create_file_dataset(self, *, name: str, file_format: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/datasets",
            json={"source": {"type": "file", "name": name, "file_format": file_format}},
        )

    async def upload_file(self, *, upload_url: str, path: Path) -> None:
        async with self._client() as client:
            response = await client.put(upload_url, content=path.read_bytes())
            _raise_for_status(response)

    async def complete_upload(self, *, name: str, file_format: str, file_path: Path, s3_key: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/datasets/upload/complete",
            json={
                "name": name,
                "file_format": file_format,
                "file_size_bytes": file_path.stat().st_size,
                "s3_key": s3_key,
            },
        )

    async def start_run(self, *, dataset_id: str, estimate: bool = False, max_rows: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "estimate": estimate,
            "column_mapping": {
                "prompt": "prompt",
                "completion": "completion",
                "context": ["context"],
                "chat": "chat_payload",
            },
            "brand_controls": {
                "length": "detailed",
                "blueprint": "Generate multilingual support-call QA data with clear policy-risk labels, escalation decisions, coaching notes, and safe support responses for Indian support teams.",
            },
            "recipe_specification": {
                "recipes": {
                    "deduplication": True,
                    "prompt_rephrase": True,
                    "reasoning_traces": False,
                }
            },
        }
        if max_rows is not None:
            payload["job_specification"] = {"max_rows": max_rows}
        return await self._request("POST", f"/datasets/{dataset_id}/run", json=payload)

    async def get_status(self, *, dataset_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/datasets/{dataset_id}/status")

    async def download(self, *, dataset_id: str, file_format: str = "jsonl") -> bytes:
        async with self._client() as client:
            response = await client.get(
                f"{self._base_url}/datasets/{dataset_id}/download",
                params={"fileFormat": file_format},
                headers=self._headers(),
            )
            _raise_for_status(response)
            return response.content

    async def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.request(
                method,
                f"{self._base_url}{path}",
                json=json,
                headers=self._headers(),
            )
            _raise_for_status(response)
            payload = response.json()
            if not isinstance(payload, dict):
                raise AdaptionClientError("Adaption API returned a non-object response")
            return payload

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def _client(self):
        if self._http_client is not None:
            return _BorrowedAsyncClient(self._http_client)
        return httpx.AsyncClient(timeout=60)


class _BorrowedAsyncClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


def _raise_for_status(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise AdaptionClientError(f"Adaption API request failed with {response.status_code}: {response.text}") from exc
