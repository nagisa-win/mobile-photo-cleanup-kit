import unittest
from phone_cleaner.core.comparator import VisualComparator
from phone_cleaner.utils.helpers import format_size, is_safe_phone_path

class TestComparator(unittest.TestCase):
    def test_format_size(self):
        self.assertEqual(format_size(500), "500 B")
        self.assertEqual(format_size(1024), "1.0 KB")
        self.assertEqual(format_size(1024 * 1024 * 5), "5.00 MB")
        self.assertEqual(format_size(1024 * 1024 * 1024 * 2), "2.00 GB")

    def test_path_safety(self):
        # 合法手机内置存储路径
        self.assertTrue(is_safe_phone_path("/storage/emulated/0/DCIM/Camera/IMG_20261113_185559.jpg"))
        self.assertTrue(is_safe_phone_path("/storage/emulated/0/Pictures/WeiXin/test.jpg"))
        
        # 非法路径（系统关键目录、遍历漏洞等）
        self.assertFalse(is_safe_phone_path("/"))
        self.assertFalse(is_safe_phone_path("/system/bin/sh"))
        self.assertFalse(is_safe_phone_path("/storage/emulated/0"))
        self.assertFalse(is_safe_phone_path("/storage/emulated/0/"))
        self.assertFalse(is_safe_phone_path("/storage/emulated/0/../../../etc/passwd"))
        self.assertFalse(is_safe_phone_path(None))

    def test_similarity_identical(self):
        # 完全相同的指纹向量
        sig1 = [10, 20, 30, 40, 50] * 10
        sig2 = [10, 20, 30, 40, 50] * 10
        sim = VisualComparator.compute_similarity(sig1, sig2)
        self.assertAlmostEqual(sim, 1.0, places=3)
        self.assertTrue(VisualComparator.is_same_image(sig1, sig2, threshold=0.88))

    def test_similarity_different(self):
        # 差异极大的正交指纹向量
        sig1 = [255 if i % 2 == 0 else 0 for i in range(100)]
        sig2 = [0 if i % 2 == 0 else 255 for i in range(100)]
        sim = VisualComparator.compute_similarity(sig1, sig2)
        self.assertLess(sim, 0.2)
        self.assertFalse(VisualComparator.is_same_image(sig1, sig2, threshold=0.88))

if __name__ == "__main__":
    unittest.main()
