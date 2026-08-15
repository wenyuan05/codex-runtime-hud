import unittest

from icon_assets import create_icon_image


class IconTests(unittest.TestCase):
    def test_mark_remains_visible_at_tray_sizes(self):
        for size in (16, 32, 48, 64, 128, 256):
            image = create_icon_image(size)
            white = sum(1 for pixel in image.getdata() if pixel[:3] == (255, 255, 255))
            self.assertGreaterEqual(white, max(8, size // 2), f"white mark missing at {size}px")

    def test_native_16px_frame_has_an_open_c_shape(self):
        """Protect the Explorer small-icon frame from regressing to a block."""
        image = create_icon_image(16)
        green = (87, 185, 126, 255)
        white = (255, 255, 255, 255)

        self.assertEqual(white, image.getpixel((4, 7)))
        self.assertEqual(white, image.getpixel((8, 4)))
        self.assertEqual(green, image.getpixel((10, 7)))


if __name__ == "__main__":
    unittest.main()
