from __future__ import annotations

from typing import Any

from .transport import UnixSocketHTTPClient


class BalloonAPI:
    def __init__(self, client: UnixSocketHTTPClient):
        self._client = client

    def put_balloon(
        self,
        *,
        amount_mib: int,
        deflate_on_oom: bool,
        stats_polling_interval_s: int = 0,
    ) -> None:
        self._validate_amount(amount_mib)
        self._validate_polling_interval(stats_polling_interval_s)
        self._client.put(
            "/balloon",
            {
                "amount_mib": amount_mib,
                "deflate_on_oom": bool(deflate_on_oom),
                "stats_polling_interval_s": stats_polling_interval_s,
            },
        )

    def patch_balloon(
        self,
        *,
        amount_mib: int,
        stats_polling_interval_s: int | None = None,
    ) -> None:
        self._validate_amount(amount_mib)
        payload = {"amount_mib": amount_mib}
        if stats_polling_interval_s is not None:
            self._validate_polling_interval(stats_polling_interval_s)
            payload["stats_polling_interval_s"] = stats_polling_interval_s
        self._client.patch("/balloon", payload)

    def get_balloon(self) -> dict[str, Any] | None:
        return self._client.get("/balloon")

    def get_statistics(self) -> dict[str, Any] | None:
        return self._client.get("/balloon/statistics")

    def _validate_amount(self, amount_mib: int) -> None:
        if not isinstance(amount_mib, int):
            raise ValueError("amount_mib must be an int")
        if amount_mib < 0:
            raise ValueError("amount_mib must be >= 0")

    def _validate_polling_interval(self, stats_polling_interval_s: int) -> None:
        if not isinstance(stats_polling_interval_s, int):
            raise ValueError("stats_polling_interval_s must be an int")
        if stats_polling_interval_s < 0:
            raise ValueError("stats_polling_interval_s must be >= 0")
