import threading


class CancellationToken:
    def __init__(self):
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def clear(self):
        self.cancel_event.clear()

    @property
    def cancelled(self):
        return self.cancel_event.is_set()
