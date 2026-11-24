"""In-memory stand-in for Supabase so tests never touch the network."""

from unittest import mock

from scripts import supabase_store as store, website_discovery


class FakeStore:
    """Patch ``supabase_store`` for one test: caches and the API log live in memory."""

    def __init__(self, test):
        self.caches: dict[str, dict] = {}
        self.log: list[dict] = []
        self.settings: dict = {}
        for name, replacement in (
            ("load_cache", lambda kind: dict(self.caches.get(kind, {}))),
            ("append_cache", lambda kind, key, result: self.caches.setdefault(kind, {}).__setitem__(key, result)),
            ("save_cache", lambda kind, results: self.caches.setdefault(kind, {}).update(results)),
            ("write_log", self.log.append),
            ("save_settings", self.settings.update),
        ):
            patcher = mock.patch.object(store, name, replacement)
            patcher.start()
            test.addCleanup(patcher.stop)
        patcher = mock.patch.object(website_discovery, "_brave_cache", None)
        patcher.start()
        test.addCleanup(patcher.stop)
