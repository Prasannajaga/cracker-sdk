import re

from .transport import UnixSocketHTTPClient
from .constant import MAC_ADDRESS_RE



class NetworkingAPI:
    def __init__(self, client: UnixSocketHTTPClient):
        self._client = client

    def network(self, *, iface_id: str, host_dev_name: str, guest_mac: str) -> None:
        self._validate_network_input(
            iface_id=iface_id,
            host_dev_name=host_dev_name,
            guest_mac=guest_mac,
        )
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

    def _validate_network_input(
        self,
        *,
        iface_id: str,
        host_dev_name: str,
        guest_mac: str,
    ) -> None:
        if not iface_id or not iface_id.strip():
            raise ValueError("iface_id must be non-empty")
        if not host_dev_name or not host_dev_name.strip():
            raise ValueError("host_dev_name must be non-empty")
        if not guest_mac or not guest_mac.strip():
            raise ValueError("guest_mac must be non-empty")
        if not MAC_ADDRESS_RE.match(guest_mac):
            raise ValueError("guest_mac must match XX:XX:XX:XX:XX:XX")
