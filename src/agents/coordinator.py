"""
`/goal` Coordinator & Git Worktree Threads (`/src/agents/coordinator.py`).
Implements Phase 4.1:
  - Top-level `/goal` Coordinator that decomposes complex architectural specs into parallel tasks.
  - Checks out real isolated local git worktrees/branches (`git worktree add -b <branch> <path>`)
    for each worker thread so parallel file edits never collide.
  - Synthesizes worker results via the shared `StructuredMemoryStore` (`memory_str_replace` with `if_version` guards)
    and returns clean `<final_answer>` summaries to the lead coordinator.
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
    """
    Orchestrates parallel worker threads across isolated `git worktree` checkouts
    and synchronizes their state into `StructuredMemoryStore`.
    """

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
        git_dir = self.repo_root / ".git"
        if not git_dir.exists():
            self._run_git(["init", "-b", "main"])
            self._run_git(["config", "user.name", "Argon Staff Architect"])
            self._run_git(["config", "user.email", "argon@heretek.ai"])
            readme = self.repo_root / "README.md"
            if not readme.exists():
                readme.write_text("# cod.ai Repository\n", encoding="utf-8")
            self._run_git(["add", "README.md"])
            self._run_git(["commit", "-m", "chore: initialize cod.ai repository root"])

    def create_isolated_worktree(self, branch_name: str, task_id: str) -> Path:
        wt_path = self.worktrees_base_dir / task_id
        if wt_path.exists():
            self._run_git(["worktree", "remove", "--force", str(wt_path)])
        # Delete branch if left over from a prior test run
        subprocess.run(["git", "branch", "-D", branch_name], cwd=str(self.repo_root), capture_output=True)
        self._run_git(["worktree", "add", "-b", branch_name, str(wt_path), "HEAD"])
        return wt_path

    def _execute_worker_in_worktree(self, subtask: GoalSubTask) -> WorktreeTaskResult:
        wt_path = self.create_isolated_worktree(subtask.branch_name, subtask.task_id)
        final_answer = subtask.worker_fn(wt_path, self.memory_store)
        self._run_git(["add", "-A"], cwd=wt_path)
        status = self._run_git(["status", "--porcelain"], cwd=wt_path)
        if status:
            self._run_git(["commit", "-m", f"feat({subtask.task_id}): {subtask.title}"], cwd=wt_path)
        commit_hash = self._run_git(["rev-parse", "--short", "HEAD"], cwd=wt_path)
        return WorktreeTaskResult(
            task_id=subtask.task_id,
            branch_name=subtask.branch_name,
            worktree_path=str(wt_path),
            commit_hash=commit_hash,
            final_answer=final_answer,
            success=True,
        )

    def execute_goal(self, goal_title: str, subtasks: list[GoalSubTask]) -> GoalSynthesisReport:
        """
        Decomposes `/goal` into isolated git worktrees, executes workers concurrently,
        and records synthesis state in shared memory.
        """
        self.memory_store.memory_write(
            "GOAL_STATE.md",
            f"# Active Goal: {goal_title}\nStatus: IN_PROGRESS\nWorkers: {len(subtasks)}\n",
        )

        # Create worktrees sequentially (git lock safety), then execute worker logic in parallel threads
        prepared: list[tuple[GoalSubTask, Path]] = []
        for st in subtasks:
            wt = self.create_isolated_worktree(st.branch_name, st.task_id)
            prepared.append((st, wt))

        def _run_prepared(item: tuple[GoalSubTask, Path]) -> WorktreeTaskResult:
            st, wt_path = item
            ans = st.worker_fn(wt_path, self.memory_store)
            self._run_git(["add", "-A"], cwd=wt_path)
            if self._run_git(["status", "--porcelain"], cwd=wt_path):
                self._run_git(["commit", "-m", f"feat({st.task_id}): {st.title}"], cwd=wt_path)
            sha = self._run_git(["rev-parse", "--short", "HEAD"], cwd=wt_path)
            return WorktreeTaskResult(
                task_id=st.task_id,
                branch_name=st.branch_name,
                worktree_path=str(wt_path),
                commit_hash=sha,
                final_answer=ans,
                success=True,
            )

        with ThreadPoolExecutor(max_workers=max(1, len(prepared))) as pool:
            results = list(pool.map(_run_prepared, prepared))

        current_mem = self.memory_store.read_memory("GOAL_STATE.md")
        summary_lines = [
            f"- `{r.task_id}` (`{r.branch_name}` @ `{r.commit_hash}`): {r.final_answer}"
            for r in results
        ]
        updated_state = self.memory_store.memory_str_replace(
            key="GOAL_STATE.md",
            old_str="Status: IN_PROGRESS",
            new_str="Status: COMPLETED\n\n## Synthesized Worker Outputs\n" + "\n".join(summary_lines),
            if_version=current_mem.version,
        )

        return GoalSynthesisReport(
            goal_title=goal_title,
            total_tasks=len(results),
            all_succeeded=all(r.success for r in results),
            worker_results=results,
            shared_memory_version=updated_state.version,
        )
