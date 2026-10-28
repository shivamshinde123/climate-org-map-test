"""Tests for the minimal, non-overwriting local environment loader."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.load_environment import load_environment


class LoadEnvironmentTests(unittest.TestCase):
    """Protect secret parsing and shell-environment precedence."""

    def test_loads_values_without_overriding_existing_environment(self):
        """Quoted file values load, while an existing process value wins."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "# comment\nOPENAI_API_KEY='local-key'\nOPENROUTER_API_KEY=file-key\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "shell-key"}, clear=True):
                loaded = load_environment(path)
                self.assertEqual(loaded, 1)
                self.assertEqual(os.environ["OPENAI_API_KEY"], "local-key")
                self.assertEqual(os.environ["OPENROUTER_API_KEY"], "shell-key")


if __name__ == "__main__":
    unittest.main()
