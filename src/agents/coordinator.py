"""
Git worktree task runner (`src/agents/coordinator.py`).

Runs each subtask in its own `git worktree` on a fresh branch, commits what the
worker changed, and records the results in the shared memory store.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
import subprocess
from typing import Callable

from src.agents.memory import StructuredMemoryStore


@dataclass
class GoalSubTask:
    task_id: str
    title: str
    branch_name: str
    worker_fn: Callable[[Path, StructuredMemoryStore], str]


@dataclass
class WorktreeTaskResult:
    task_id: str
    branch_name: str
    worktree_path: str
    commit_hash: str
    final_answer: str
    success: bool


@dataclass
class GoalSynthesisReport:
    goal_title: str
    total_tasks: int
    all_succeeded: bool
    worker_results: list[WorktreeTaskResult] = field(default_factory=list)
    shared_memory_version: int = 0


class GoalWorktreeCoordinator:
    """Runs workers in parallel, each in its own `git worktree`, and records the results in a `StructuredMemoryStore`."""

    def __init__(self, repo_root: str | Path, worktrees_base_dir: str | Path, memory_store: StructuredMemoryStore) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.worktrees_base_dir = Path(worktrees_base_dir).resolve()
        self.worktrees_base_dir.mkdir(parents=True, exist_ok=True)
        self.memory_store = memory_store
        self._ensure_git_repo()

    def _run_git(self, args: list[str], cwd: Path | None = None) -> str:
        proc = subprocess.run(
            ["git"] + args,
            cwd=str(cwd or self.repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout.strip()

    def _ensure_git_repo(self) -> None:
        self.repo_root.mkdir(parents=True, exist_ok=True)
        if not (self.repo_root / ".git").exists():
            self._run_git(["init", "-b", "main"])
            self._run_git(["config", "user.name", "cod.ai"])
            self._run_git(["config", "user.email", "cod@localhost"])
            readme = self.repo_root / "README.md"
            if not readme.exists():
                readme.write_text("# Repository\n", encoding="utf-8")
            self._run_git(["add", "README.md"])
            self._run_git(["commit", "-m", "Initial commit"])

    def create_isolated_worktree(self, branch_name: str, task_id: str) -> Path:
        wt_path = self.worktrees_base_dir / task_id
        if wt_path.exists():
            self._run_git(["worktree", "remove", "--force", str(wt_path)])
        # A branch left over from an earlier run would make `worktree add -b` fail.
        subprocess.run(["git", "branch", "-D", branch_name], cwd=str(self.repo_root), capture_output=True)
        self._run_git(["worktree", "add", "-b", branch_name, str(wt_path), "HEAD"])
        return wt_path

    def _run_worker(self, subtask: GoalSubTask, wt_path: Path) -> WorktreeTaskResult:
        """Runs one worker in its worktree and commits what it changed. A worker that raises is reported as failed."""
        try:
            answer = subtask.worker_fn(wt_path, self.memory_store)
            success = True
        except Exception as exc:
            answer = f"failed: {type(exc).__name__}: {exc}"
            success = False
        self._run_git(["add", "-A"], cwd=wt_path)
        if self._run_git(["status", "--porcelain"], cwd=wt_path):
            self._run_git(["commit", "-m", f"{subtask.task_id}: {subtask.title}"], cwd=wt_path)
        sha = self._run_git(["rev-parse", "--short", "HEAD"], cwd=wt_path)
        return WorktreeTaskResult(
            task_id=subtask.task_id,
            branch_name=subtask.branch_name,
            worktree_path=str(wt_path),
            commit_hash=sha,
            final_answer=answer,
            success=success,
        )

    def execute_goal(self, goal_title: str, subtasks: list[GoalSubTask]) -> GoalSynthesisReport:
        """
        Runs each subtask's worker in parallel in its own worktree and records the
        goal's status and each worker's answer in `GOAL_STATE.md`.
        """
        self.memory_store.memory_write(
            "GOAL_STATE.md",
            f"# Active Goal: {goal_title}\nStatus: IN_PROGRESS\nWorkers: {len(subtasks)}\n",
        )

        # Worktrees are created one at a time because git takes a lock; workers then run in parallel.
        prepared: list[tuple[GoalSubTask, Path]] = []
        for st in subtasks:
            wt = self.create_isolated_worktree(st.branch_name, st.task_id)
            prepared.append((st, wt))

        with ThreadPoolExecutor(max_workers=max(1, len(prepared))) as pool:
            results = list(pool.map(lambda item: self._run_worker(*item), prepared))

        current_mem = self.memory_store.read_memory("GOAL_STATE.md")
        all_succeeded = all(r.success for r in results)
        summary_lines = [
            f"- `{r.task_id}` (`{r.branch_name}` @ `{r.commit_hash}`): {r.final_answer}"
            for r in results
        ]
        updated_state = self.memory_store.memory_str_replace(
            key="GOAL_STATE.md",
            old_str="Status: IN_PROGRESS",
            new_str=f"Status: {'COMPLETED' if all_succeeded else 'FAILED'}\n\n## Worker results\n" + "\n".join(summary_lines),
            if_version=current_mem.version,
        )

        return GoalSynthesisReport(
            goal_title=goal_title,
            total_tasks=len(results),
            all_succeeded=all_succeeded,
            worker_results=results,
            shared_memory_version=updated_state.version,
        )
