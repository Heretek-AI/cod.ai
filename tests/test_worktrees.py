"""Tests for the versioned memory store and the git worktree task runner (`src/agents/`)."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

from src.agents import GoalSubTask, GoalWorktreeCoordinator, MemoryConcurrencyError, MemoryMatchError, StructuredMemoryStore


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.mem = StructuredMemoryStore(self.tmp / "memory")

    def tearDown(self):
        self._tmp.cleanup()

    def test_versions_guard_concurrent_writes(self):
        self.assertEqual(self.mem.memory_write("ARCH.md", "Status: DRAFT\nModule: Core\n").version, 1)
        with self.assertRaises(MemoryConcurrencyError):
            self.mem.memory_str_replace("ARCH.md", "Status: DRAFT", "Status: FINAL", if_version=99)
        self.assertEqual(self.mem.memory_append("ARCH.md", "Status: DRAFT\n", if_version=1).version, 2)
        with self.assertRaises(MemoryMatchError):
            self.mem.memory_str_replace("ARCH.md", "Status: DRAFT", "Status: FINAL", if_version=2)
        state = self.mem.memory_str_replace("ARCH.md", "Module: Core", "Module: Verified", if_version=2)
        self.assertEqual(state.version, 3)
        self.assertIn("Module: Verified", self.mem.read_memory("ARCH.md").content)

    def test_keys_stay_inside_the_memory_root(self):
        with self.assertRaises(ValueError):
            self.mem.memory_write("../escape.md", "x")
        with self.assertRaises(ValueError):
            self.mem.memory_write("/etc/passwd", "x")
        self.assertEqual(self.mem.memory_write("notes/a.md", "ok").version, 1)


class WorktreeCoordinatorTests(unittest.TestCase):
    def test_workers_run_in_separate_worktrees(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            mem = StructuredMemoryStore(tmp / "memory")
            coordinator = GoalWorktreeCoordinator(tmp / "repo", tmp / "worktrees", mem)

            def worker(name):
                def run(worktree: Path, memory: StructuredMemoryStore) -> str:
                    (worktree / f"{name}.py").write_text(f"{name.upper()} = True\n", encoding="utf-8")
                    return f"wrote {name}.py"
                return run

            def broken(worktree: Path, memory: StructuredMemoryStore) -> str:
                raise RuntimeError("boom")

            report = coordinator.execute_goal("Two features", [
                GoalSubTask("task_a", "Feature A", "feat/a", worker("feature_a")),
                GoalSubTask("task_b", "Feature B", "feat/b", worker("feature_b")),
            ])
            self.assertTrue(report.all_succeeded)
            self.assertEqual(report.total_tasks, 2)
            self.assertIn("Status: COMPLETED", mem.read_memory("GOAL_STATE.md").content)
            for result, other in zip(report.worker_results, ("feature_b", "feature_a")):
                files = subprocess.run(["git", "ls-tree", "--name-only", result.branch_name], cwd=tmp / "repo", capture_output=True, text=True).stdout
                self.assertNotIn(other, files)

            failed = coordinator.execute_goal("Broken", [GoalSubTask("task_c", "Broken", "feat/c", broken)])
            self.assertFalse(failed.all_succeeded)
            self.assertIn("boom", failed.worker_results[0].final_answer)
            self.assertIn("Status: FAILED", mem.read_memory("GOAL_STATE.md").content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
