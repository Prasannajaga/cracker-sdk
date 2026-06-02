from .transport import UnixSocketHTTPClient


class RuntimeAPI:
    def __init__(self, client: UnixSocketHTTPClient):
        self._client = client

    def pause(self) -> None:
        self._client.patch("/vm", {"state": "Paused"})

    def resume(self) -> None:
        self._client.patch("/vm", {"state": "Resumed"})

    def send_ctrl_alt_del(self) -> None:
        self._client.put("/actions", {"action_type": "SendCtrlAltDel"})
