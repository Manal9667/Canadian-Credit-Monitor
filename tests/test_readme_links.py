from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


class ReadmeLinkTests(unittest.TestCase):
    def test_relative_links_in_readmes_resolve(self) -> None:
        for readme in (ROOT / "README.md", ROOT / "documentation" / "technical_reference.md"):
            with self.subTest(readme=readme.name):
                text = readme.read_text(encoding="utf-8")
                for raw_target in LINK.findall(text):
                    target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
                    parsed = urlsplit(target)
                    if parsed.scheme or target.startswith("#"):
                        continue
                    local_path = unquote(parsed.path)
                    if not local_path:
                        continue
                    resolved = (readme.parent / local_path).resolve()
                    self.assertTrue(
                        resolved.exists(),
                        f"{readme.name} has a broken local link: {raw_target}",
                    )


if __name__ == "__main__":
    unittest.main()
