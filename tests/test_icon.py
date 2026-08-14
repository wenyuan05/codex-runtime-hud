import unittest

from icon_assets import create_icon_image


class IconTests(unittest.TestCase):
    def test_mark_remains_visible_at_tray_sizes(self):
        for size in (16, 32, 48, 64, 128, 256):
            image = create_icon_image(size)
            white = sum(1 for pixel in image.getdata() if pixel[:3] == (255, 255, 255))
            self.assertGreaterEqual(white, max(8, size // 2), f"white mark missing at {size}px")


if __name__ == "__main__":
    unittest.main()

