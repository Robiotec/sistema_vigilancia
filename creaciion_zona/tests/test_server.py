from __future__ import annotations

import unittest

from editor_zona.config import STATIC_DIR
from editor_zona.server import parse_byte_range, render_index_html, resolve_static_asset


class ServerHelpersTest(unittest.TestCase):
    def test_render_index_html_injects_escaped_video_name(self) -> None:
        html = render_index_html('video "demo".mp4').decode("utf-8")

        self.assertIn('data-video-name="video &quot;demo&quot;.mp4"', html)
        self.assertIn('/static/js/main.js', html)

    def test_resolve_static_asset_accepts_known_asset(self) -> None:
        asset_path = resolve_static_asset("/static/js/main.js")

        self.assertEqual(asset_path, (STATIC_DIR / "js" / "main.js").resolve())

    def test_resolve_static_asset_rejects_path_traversal(self) -> None:
        self.assertIsNone(resolve_static_asset("/static/../secret.txt"))

    def test_parse_byte_range_accepts_open_ended_range(self) -> None:
        self.assertEqual(parse_byte_range("bytes=100-", 500), (100, 499))

    def test_parse_byte_range_accepts_suffix_range(self) -> None:
        self.assertEqual(parse_byte_range("bytes=-50", 500), (450, 499))

    def test_parse_byte_range_rejects_invalid_range(self) -> None:
        self.assertIsNone(parse_byte_range("bytes=600-700", 500))


if __name__ == "__main__":
    unittest.main()
