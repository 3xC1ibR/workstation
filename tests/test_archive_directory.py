import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "archive_directory", Path(__file__).parents[1] / "scripts/archive_directory.py"
)
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


class ArchiveIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = self.directory / "source"
        self.source.mkdir()
        (self.source / "nested/empty").mkdir(parents=True)
        (self.source / "nested/data.bin").write_bytes(bytes(range(256)) * 1000)
        (self.source / ".hidden").write_text("hidden content\n")
        (self.source / "nested/link").symlink_to("data.bin")
        (self.source / "external-link").symlink_to("/unavailable/external-file")
        os.link(self.source / ".hidden", self.source / "hard-link")
        os.chmod(self.source / ".hidden", 0o640)
        self.entries = archive.inventory(self.source)
        self.archive = self.directory / "contents.tar.zst"

    def create_archive(self):
        subprocess.run(["tar", "--format", "pax", "--acls", "--xattrs", "--zstd",
                        "-cf", self.archive, "-C", self.source, "."], check=True)

    def record(self):
        return {"source": str(self.source), "snapshot": "test", "source_bytes": 256015,
                "bucket": "test", "object_key": "test", "version_id": "test",
                "archive_sha256": "test", "entries": self.entries,
                "verification": "downloaded_sha256_and_all_file_contents"}

    def test_archive_and_restoration_preserve_contents_links_and_empty_directories(self):
        subprocess.run(["xattr", "-w", "com.example.archive-test", "metadata", self.source / ".hidden"], check=True)
        self.entries = archive.inventory(self.source)
        self.create_archive()
        archive.verify_archive(self.archive, self.entries)
        destination = self.directory / "restored"
        destination.mkdir()
        subprocess.run(["tar", "-xpf", self.archive, "-C", destination], check=True)
        restored = archive.inventory(destination)
        self.assertEqual(set(restored), set(self.entries))
        for name, expected in self.entries.items():
            for field in ["type", "mode", "sha256", "target"]:
                self.assertEqual(expected.get(field), restored[name].get(field))
        self.assertEqual(subprocess.check_output(["xattr", "-p", "com.example.archive-test", destination / ".hidden"]).strip(), b"metadata")

    def test_corrupt_content_is_rejected(self):
        (self.source / ".hidden").write_text("different content\n")
        self.create_archive()
        with self.assertRaisesRegex(RuntimeError, "mismatch"):
            archive.verify_archive(self.archive, self.entries)

    def test_missing_archive_member_is_rejected(self):
        (self.source / "nested/link").unlink()
        self.create_archive()
        with self.assertRaisesRegex(RuntimeError, "missing"):
            archive.verify_archive(self.archive, self.entries)

    def test_changed_or_new_files_prevent_any_removal(self):
        (self.source / "new-file").write_text("new work")
        with self.assertRaisesRegex(RuntimeError, "New source"):
            archive.evict(self.source, self.record())
        self.assertTrue((self.source / ".hidden").exists())
        (self.source / "new-file").unlink()
        (self.source / ".hidden").write_text("changed")
        with self.assertRaisesRegex(RuntimeError, "changed"):
            archive.evict(self.source, self.record())
        self.assertTrue((self.source / "nested/data.bin").exists())

    def test_unverified_archive_cannot_remove_local_files(self):
        record = self.record()
        record.pop("verification")
        with self.assertRaisesRegex(RuntimeError, "verification"):
            archive.evict(self.source, record)
        self.assertTrue((self.source / ".hidden").exists())

    def test_eviction_preserves_directory_tree_and_records(self):
        archive.evict(self.source, self.record())
        self.assertTrue((self.source / "nested/empty").is_dir())
        self.assertFalse(os.path.lexists(self.source / "external-link"))
        self.assertFalse((self.source / "nested/data.bin").exists())
        self.assertEqual(json.loads((self.source / "ARCHIVE.json").read_text())["status"], "archived")
        self.assertIn("nested/data.bin", (self.source / "FILE_INDEX.txt").read_text())

    def test_archive_path_traversal_is_rejected(self):
        for name in ["../escape", "/absolute", "directory/../../escape"]:
            with self.assertRaises(RuntimeError):
                archive.archive_member_name(name)


if __name__ == "__main__":
    unittest.main()
