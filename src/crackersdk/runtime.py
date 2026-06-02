from .transport import UnixSocketHTTPClient


class RuntimeAPI:
    def __init__(self, client: UnixSocketHTTPClient):
        self._client = client

    def pause(self) -> None:
        self._client.put("/actions", {"action_type": "Pause"})

    def resume(self) -> None:
        self._client.put("/actions", {"action_type": "Resume"})

    def send_ctrl_alt_del(self) -> None:
        self._client.put("/actions", {"action_type": "SendCtrlAltDel"})
