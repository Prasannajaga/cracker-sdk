class FirecrackerError(Exception):
    pass


class FirecrackerAPIError(FirecrackerError):
    pass


class FirecrackerProcessError(FirecrackerError):
    pass


class FirecrackerTimeoutError(FirecrackerError):
    pass
