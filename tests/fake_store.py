"""In-memory stand-in for Supabase so tests never touch the network."""

from unittest import mock

from scripts import supabase_store as store, website_discovery


class FakeStore:
    """Patch ``supabase_store`` for one test: caches, the API log and survey evidence live in memory."""

    def __init__(self, test, survey: dict | None = None):
        self.caches: dict[str, dict] = {}
        self.log: list[dict] = []
        for name, replacement in (
            ("load_cache", lambda kind: dict(self.caches.get(kind, {}))),
            ("append_cache", lambda kind, key, result: self.caches.setdefault(kind, {}).__setitem__(key, result)),
            ("write_log", self.log.append),
            ("survey_verifications", lambda: dict(survey or {})),
        ):
            patcher = mock.patch.object(store, name, replacement)
            patcher.start()
            test.addCleanup(patcher.stop)
        patcher = mock.patch.object(website_discovery, "_brave_cache", None)
        patcher.start()
        test.addCleanup(patcher.stop)
