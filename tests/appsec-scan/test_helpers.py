"""Unit tests of appsec-scan helpers.py inventory. No network; standard library only.

    python3 -m unittest discover -s tests/appsec-scan -p 'test_*.py' -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "plugins", "appsec-scan", "skills", "appsec-scan", "lib"))
import helpers  # noqa: E402


@unittest.skipIf(os.name == "nt", "symlinks need extra privileges on Windows")
class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="appsec-helpers-")
        self.root = os.path.join(self.dir, "repo")
        self.outside = os.path.join(self.dir, "outside")
        self.out = os.path.join(self.dir, "inv")
        for d in (self.root, self.outside, self.out):
            os.makedirs(d)
        with open(os.path.join(self.outside, "requirements.txt"), "w", encoding="utf-8") as f:
            f.write("secret-outside==1.0\nunpinned\n")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_parent_directory_symlink_is_external(self):
        # deps/ points outside: deps/requirements.txt is a regular file, but it is outside the repository
        os.symlink(self.outside, os.path.join(self.root, "deps"))
        with open(os.path.join(self.root, "app.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n")
        files = iter(["app.py", "deps/requirements.txt"])
        orig = helpers.tree_files
        helpers.tree_files = lambda root: files
        try:
            helpers.inventory("tree", self.root, self.out)
        finally:
            helpers.tree_files = orig
        with open(os.path.join(self.out, "inventory.json"), encoding="utf-8") as f:
            inv = json.load(f)
        self.assertEqual([(s["path"], s["critical"]) for s in inv["external_symlinks"]], [("deps/requirements.txt", "lockfile")])
        self.assertEqual(inv["lockfiles"], [])
        self.assertEqual(inv["unpinned"], [])
        self.assertFalse(os.path.exists(os.path.join(self.out, "locks", "deps")))


if __name__ == "__main__":
    unittest.main()
