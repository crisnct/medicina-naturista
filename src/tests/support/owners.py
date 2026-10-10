"""Persistent synthetic owner ledger shared explicitly across test app restarts."""

import threading


class FakeOwnerRepository:
    def __init__(self):
        self.rows = {}
        self.lock = threading.Lock()

    def issue(self, token_hash):
        with self.lock:
            self.rows[token_hash] = False

    def active(self, token_hash):
        with self.lock:
            return token_hash in self.rows and not self.rows[token_hash]

    def revoke(self, token_hash):
        with self.lock:
            if token_hash in self.rows:
                self.rows[token_hash] = True

    def close(self):
        pass
