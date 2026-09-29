"""Behavior tests in temporary repositories; never touch the caller's Git state."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        script = Path(__file__).resolve().parent / "context.py"
        if not script.exists():
            script = Path(__file__).resolve().parent.parent / "context.py"
        (self.root / ".agents/skills/project-context").mkdir(parents=True)
        (self.root / ".claude/skills/project-context").mkdir(parents=True)
        shutil.copyfile(script, self.root / ".agents/context.py")
        for name, content in {
            "AGENTS.md": "Read .agents/workflow.md\n",
            "CLAUDE.md": "@AGENTS.md\n",
            ".gitignore": ".agents/state/\n",
            ".agents/workflow.md": "test workflow\n",
            ".agents/skills/project-context/SKILL.md": "test skill\n",
            ".claude/skills/project-context/SKILL.md": "test skill\n",
        }.items():
            (self.root / name).write_text(content)
        data = {"schema_version": 1, "project": "test", "repository": "github.com/test/one",
                "ecosystem": "test", "architecture": "fixture", "tracker": "existing issue",
                "sources": ["AGENTS.md"], "gates": ["fixture gate"],
                "toolkit_files": {".agents/workflow.md": hashlib.sha256(b"test workflow\n").hexdigest()}}
        (self.root / ".agents/project.json").write_text(json.dumps(data))
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Context Test")
        self.git("remote", "add", "origin", "git@github.com:test/one.git")
        self.git("add", ".")
        self.git("-c", "core.hooksPath=/dev/null", "commit", "-m", "fixture")
        self.payload = self.root.parent / "payload.json"
        self.payload.write_text(json.dumps({name: "reviewed facts" for name in
            ["objective", "authorization", "decisions", "next_step", "evidence", "risks"]}))

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout

    def run_tool(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(self.root / ".agents/context.py"), *args],
                                cwd=self.root.parent, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0 if ok else 1, result.stdout + result.stderr)
        return json.loads(result.stdout) if ok else result.stderr

    def save(self, task="task-one", ok=True):
        return self.run_tool("checkpoint", "--task", task, "--from-file", str(self.payload), ok=ok)

    def test_check_and_roundtrip_from_another_cwd(self):
        before = self.git("status", "--porcelain")
        self.assertTrue(self.run_tool("check")["ok"])
        self.save()
        result = self.run_tool("resume", "--task", "task-one")
        self.assertFalse(result["stale"])
        self.assertEqual(result["checkpoint"]["handoff"]["objective"], "reviewed facts")
        self.assertEqual(before, self.git("status", "--porcelain"))

    def test_changed_tracked_content_is_stale(self):
        self.save()
        (self.root / "AGENTS.md").write_text("changed .agents/workflow.md")
        self.assertTrue(self.run_tool("resume", "--task", "task-one")["stale"])

    def test_changed_untracked_content_is_stale(self):
        new = self.root / "new.txt"
        new.write_text("first")
        self.save()
        new.write_text("other")
        self.assertTrue(self.run_tool("resume", "--task", "task-one")["stale"])

    def test_redistributed_bytes_between_untracked_files_are_stale(self):
        first, second = self.root / "first.txt", self.root / "second.txt"
        first.write_text("a")
        second.write_text("bc")
        self.save()
        first.write_text("ab")
        second.write_text("c")
        self.assertTrue(self.run_tool("resume", "--task", "task-one")["stale"])

    def test_branch_change_is_stale(self):
        self.save()
        self.git("checkout", "-b", "another")
        self.assertTrue(self.run_tool("resume", "--task", "task-one")["stale"])

    def test_new_product_before_first_commit(self):
        self.git("checkout", "--orphan", "new-product")
        self.git("rm", "-r", "--cached", ".")
        self.assertEqual(self.run_tool("resume")["checkout"]["head"], "UNBORN")
        self.save()
        self.assertFalse(self.run_tool("resume", "--task", "task-one")["stale"])

    def test_cross_repository_checkpoint_rejected(self):
        self.save()
        p = self.root / ".agents/state/task-one.json"
        data = json.loads(p.read_text())
        data["repository"] = "github.com/other/product"
        p.write_text(json.dumps(data))
        self.assertIn("another repository", self.run_tool("resume", "--task", "task-one", ok=False))

    def test_origin_mismatch_rejected(self):
        self.git("remote", "set-url", "origin", "https://github.com/other/product.git")
        self.run_tool("check", ok=False)

    def test_equivalent_remote_urls(self):
        for remote in ["https://github.com/test/one.git/", "ssh://git@github.com/test/one.git/",
                       "git@github.com:test/one.git", "https://github.com/test/one"]:
            with self.subTest(remote=remote):
                self.git("remote", "set-url", "origin", remote)
                self.assertTrue(self.run_tool("check")["ok"])

    def test_probe_only_ignore_does_not_allow_real_checkpoint(self):
        (self.root / ".gitignore").write_text(".agents/state/probe.json\n")
        self.assertIn("actual checkpoint path", self.save(ok=False))
        self.assertFalse((self.root / ".agents/state/task-one.json").exists())

    def test_path_traversal_and_symlink_rejected(self):
        self.save("../escape", ok=False)
        directory = self.root / ".agents/state"
        directory.mkdir()
        (directory / "task-one.json").symlink_to(self.root / "AGENTS.md")
        before = (self.root / "AGENTS.md").read_text()
        self.save(ok=False)
        self.assertEqual(before, (self.root / "AGENTS.md").read_text())

    def test_directory_symlink_rejected(self):
        (self.root / ".agents/state").symlink_to(self.root.parent, target_is_directory=True)
        self.save(ok=False)

    def test_missing_source_and_workflow_drift_rejected(self):
        (self.root / ".agents/workflow.md").write_text("drift")
        self.run_tool("check", ok=False)
        (self.root / "AGENTS.md").unlink()
        self.run_tool("resume", ok=False)

    def test_invalid_payload_and_secret_rejected(self):
        self.payload.write_text('{"objective": "incomplete"}')
        self.save(ok=False)
        self.payload.write_text(json.dumps({name: "Bearer " + "x" * 25 for name in
            ["objective", "authorization", "decisions", "next_step", "evidence", "risks"]}))
        self.save(ok=False)

    def test_missing_ignore_and_adapter_drift_rejected(self):
        (self.root / ".gitignore").write_text("")
        self.run_tool("check", ok=False)
        (self.root / ".gitignore").write_text(".agents/state/\n")
        (self.root / ".claude/skills/project-context/SKILL.md").write_text("different")
        self.run_tool("check", ok=False)


if __name__ == "__main__":
    unittest.main()
