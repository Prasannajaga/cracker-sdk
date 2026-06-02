from .transport import UnixSocketHTTPClient


class NetworkingAPI:
    def __init__(self, client: UnixSocketHTTPClient):
        self._client = client

    def network(self, *, iface_id: str, host_dev_name: str, guest_mac: str) -> None:
        self._client.put(
            f"/network-interfaces/{iface_id}",
            {
                "iface_id": iface_id,
                "host_dev_name": host_dev_name,
                "guest_mac": guest_mac,
            },
        )

    def entropy(self) -> None:
        self._client.put("/entropy", {})
