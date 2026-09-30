from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sensor_lite.pages import build_static_site


class PagesTests(unittest.TestCase):
    def test_builds_relative_static_site(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with patch("sensor_lite.pages.build_demo", return_value={"project": {"name": "test"}}):
                build_static_site(output)

            index = (output / "index.html").read_text(encoding="utf-8")
            app = (output / "app.js").read_text(encoding="utf-8")

            self.assertIn('content="./demo.json"', index)
            self.assertIn('href="./styles.css"', index)
            self.assertIn('src="./app.js"', index)
            self.assertIn('fetch(staticDataUrl || "/api/demo")', app)
            self.assertEqual(
                (output / "demo.json").read_text(encoding="utf-8"),
                '{\n  "project": {\n    "name": "test"\n  }\n}\n',
            )
            self.assertTrue((output / ".nojekyll").exists())


if __name__ == "__main__":
    unittest.main()
