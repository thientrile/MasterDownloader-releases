import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PyQt6.QtWidgets import QApplication
    import App
    _HAVE_QT = True
except Exception:
    _HAVE_QT = False


@unittest.skipUnless(_HAVE_QT, "PyQt6 khong san co")
class DialogResurrectedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_resurrected_files_are_selectable(self):
        groups = [["/keep/a.jpg", "/dup/a.jpg"]]
        resurrected = ["/old/clip.mp4"]
        dlg = App.DuplicatesDialog(groups, resurrected=resurrected)
        selected = dlg.selected_paths()
        self.assertIn("/dup/a.jpg", selected)
        self.assertIn("/old/clip.mp4", selected)
        self.assertNotIn("/keep/a.jpg", selected)


if __name__ == "__main__":
    unittest.main()
