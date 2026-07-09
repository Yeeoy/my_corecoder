import threading


class CancellationToken:
    def __init__(self, parent_token: "CancellationToken | None" = None):
        self.cancel_event = threading.Event()
        self.parent_token = parent_token

    def cancel(self):
        self.cancel_event.set()

    def clear(self):
        self.cancel_event.clear()

    @property
    def cancelled(self):
        return self.cancel_event.is_set() or (self.parent_token is not None and self.parent_token.cancelled)
