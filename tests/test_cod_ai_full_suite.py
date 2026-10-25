#!/usr/bin/env python3
"""
Comprehensive Adversarial Verification Suite for `cod.ai` (Phases 1.5, 2, 3, 4, and 5).
Tests every non-negotiable architectural invariant, edge case, concurrency guard,
and headless browser telemetry rendering.
"""
import json
import os
from pathlib import Path
import tempfile
import unittest

import sys
if "/home/spark" not in sys.path:
    sys.path.insert(0, "/home/spark")
WORKSPACE = Path(__file__).resolve().parent.parent
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from src.prompts import (
    AbstractionPolicy,
    HolisticWebArchitectEngine,
    PolarityMode,
    PromptAssemblyEngine,
    TruncationViolationError,
    build_simple_mode_prompt,
    is_simple_mode_enabled,
    validate_surgical_bash_command,
    verify_zero_truncation,
)
from src.context import (
    FiveMinuteTTLScheduler,
    HybridContextGovernor,
    ModelAffinityRouter,
    ModelSwitchCacheViolationError,
    PrefixMutationError,
    ThreeLayerCacheAssembler,
    ToolDefinition,
    get_min_cache_tokens,
)
from src.agents import (
    AdversarialVerificationAgent,
    CompactionValidationError,
    DiscoveryQuery,
    GoalSubTask,
    GoalWorktreeCoordinator,
    MemoryConcurrencyError,
    MemoryMatchError,
    PiSessionDAG,
    ReadOnlyExploreSubAgent,
    ReadOnlyViolationError,
    StructuredMemoryStore,
    TwoTierCompactionEngine,
    VerifierPermissionError,
)
from src.security import (
    CredentialVaultProxy,
    PluggableSandboxRunner,
    SecurityPolicyConfig,
    SkillDoctorTelemetryEngine,
    TwoStageSecurityClassifier,
)


class TestPhase2DualPolarityPrompts(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PromptAssemblyEngine(workspace_root=str(WORKSPACE))

    def test_layer1_static_prefix_immutability_and_zero_timestamps(self) -> None:
        p1 = self.engine.build_static_layer1_system_prompt(deferred_tool_names=["mcp_github", "mcp_postgres"])
        p2 = self.engine.build_static_layer1_system_prompt(deferred_tool_names=["mcp_postgres", "mcp_github"])
        self.assertEqual(p1, p2)
        # Verify mutating deferred tool catalog mid-session raises Invariant #1 RuntimeError
        with self.assertRaises(RuntimeError):
            self.engine.build_static_layer1_system_prompt(deferred_tool_names=["mcp_mutated"])

    def test_mode_a_iterative_drafting_over_100_lines_and_anti_truncation(self) -> None:
        arch = HolisticWebArchitectEngine()
        # Verify placeholder detection rejects truncated code
        bad_code = "def foo():\n    // rest of code...\n    return 1\n"
        ok, violations = verify_zero_truncation(bad_code)
        self.assertFalse(ok)
        self.assertTrue(any("rest of" in v for v in violations))

        # Verify 4-stage iterative drafting produces >100 lines with zero placeholders
        sections = [
            ("Section 1: Domain Models", lambda: "\n".join(f"FIELD_{i} = {i}" for i in range(40))),
            ("Section 2: Core State Machine", lambda: "\n".join(f"STATE_{i} = 'ACTIVE_{i}'" for i in range(40))),
            ("Section 3: Boundary Validators", lambda: "\n".join(f"def validate_{i}(x): return x == {i}" for i in range(35))),
        ]
        artifact = arch.orchestrate_iterative_draft(
            identifier="core-orchestrator-v1",
            title="Core Orchestrator Module",
            target_path="src/core_orchestrator.py",
            section_specs=sections,
            enforce_over_100_lines=True,
        )
        self.assertGreater(artifact.line_count, 100)
        self.assertIn('<antArtifact identifier="core-orchestrator-v1"', artifact.to_ant_artifact_xml())

        # Verify TruncationViolationError is raised if a section emits TODO: implement
        with self.assertRaises(TruncationViolationError):
            arch.orchestrate_iterative_draft(
                identifier="bad-artifact",
                title="Bad",
                target_path="src/bad.py",
                section_specs=[("Sec1", lambda: "# TODO: implement later\n" * 105)],
            )

    def test_mode_b_surgical_cli_bans_bash_file_manipulation(self) -> None:
        for forbidden_cmd in [
            "cat src/cli.py",
            "head -n 20 README.md",
            "tail -f app.log",
            "sed -i 's/foo/bar/g' src/cli.py",
            "awk '{print $1}' data.txt",
            "pytest && cat results.txt",
            "echo 'hello' > src/hacked.py",
        ]:
            res = validate_surgical_bash_command(forbidden_cmd)
            self.assertFalse(res.allowed, f"Expected '{forbidden_cmd}' to be blocked in Mode B")

        for allowed_cmd in [
            "pytest tests/ -v",
            "python3 -m unittest discover -s tests",
            "git status --porcelain",
        ]:
            res = validate_surgical_bash_command(allowed_cmd)
            self.assertTrue(res.allowed, f"Expected '{allowed_cmd}' to be allowed in Mode B")

    def test_abstraction_override_and_pi_specialist_loader(self) -> None:
        spec = self.engine.load_pi_specialist("holistic-web-architect")
        self.assertEqual(spec.slug, "holistic-web-architect")
        self.assertIn("Mode A", spec.charter_markdown)

        reminder = self.engine.build_layer3_polarity_switch(
            mode=PolarityMode.MODE_B_IMPLEMENTER,
            context="Repo execution",
            objective="Implement cache assembler",
            project_instructions="CLAUDE.md: authorize_modular_helpers and authorize_clean_abstractions",
            skill_domains=["system_architecture", "pi_specialist_bridge"],
            pi_specialist_slug="adversarial-verifier",
        )
        self.assertIn('status="AUTHORIZED_BY_ARCHITECT_OR_AGENTS_MD"', reminder)
        self.assertIn('<pi_specialist_charter slug="adversarial-verifier">', reminder)

    def test_cod_simple_mode_4_line_override(self) -> None:
        self.assertTrue(is_simple_mode_enabled({"COD_SIMPLE": "true"}))
        simple_prompt = build_simple_mode_prompt(cwd="/workspace", fixed_date="2026-10-24")
        self.assertEqual(len(simple_prompt.splitlines()), 4)
        self.assertIn("Identity:", simple_prompt)
        self.assertIn("CWD: /workspace", simple_prompt)


class TestPhase3ContextAndCacheEngine(unittest.TestCase):
    def test_3_layer_cache_assembler_and_thresholds(self) -> None:
        self.assertEqual(get_min_cache_tokens("claude-opus-5-5"), 512)
        self.assertEqual(get_min_cache_tokens("claude-sonnet-4-6"), 1024)
        self.assertEqual(get_min_cache_tokens("claude-opus-4-7"), 2048)
        self.assertEqual(get_min_cache_tokens("claude-haiku-4-5"), 4096)

        core_tools = [
            ToolDefinition("Read", "Read file contents", {"type": "object", "properties": {"path": {"type": "string"}}}),
            ToolDefinition("Edit", "Edit file contents", {"type": "object", "properties": {"path": {"type": "string"}}}),
        ]
        deferred_tools = [
            ToolDefinition("mcp_github_create_pr", "Create GitHub PR", {"type": "object"}, defer_loading=True),
            ToolDefinition("mcp_postgres_query", "Run SQL query on Postgres", {"type": "object"}, defer_loading=True),
        ]

        # Verify deferred tool cannot carry cache_control (Anthropic 400 error rule)
        with self.assertRaises(ValueError):
            deferred_tools[0].to_api_dict(with_cache_control=True)

        assembler = ThreeLayerCacheAssembler(
            model="claude-haiku-4-5",  # 4,096 min token threshold test
            system_prompt="You are cod.ai.",
            layer2_project_context="# CLAUDE.md\nAlways preserve prefix caches.",
            core_tools=core_tools,
            deferred_tools=deferred_tools,
            auto_pad_to_min_threshold=True,
        )
        assembler.append_user_message(
            "Implement Postgres query handler",
            system_reminders=["Remember to use parameterized SQL."],
        )
        req1 = assembler.assemble_request()
        self.assertTrue(req1.cache_eligible_layer1)
        self.assertTrue(req1.cache_eligible_layer2)
        self.assertGreaterEqual(req1.layer1_tokens, 4096)
        self.assertGreaterEqual(req1.layer2_tokens, 4096)
        self.assertLessEqual(req1.breakpoint_count, 4)

        # Inject dynamic MCP tool in Layer 3 and turn-scoped system reminder; verify Layer 1 & Layer 2 hashes never change!
        refs = assembler.search_deferred_tools("postgres sql")
        self.assertEqual(refs[0]["tool_name"], "mcp_postgres_query")
        assembler.inject_dynamic_mcp_tool_layer3(
            ToolDefinition("mcp_sentry_issues", "Fetch Sentry issues", {"type": "object"})
        )
        assembler.append_turn_scoped_system_reminder("Request independent reads in one turn.")
        req2 = assembler.assemble_request()
        self.assertEqual(req1.layer1_hash, req2.layer1_hash)
        self.assertEqual(req1.layer2_hash, req2.layer2_hash)

    def test_5_minute_ttl_scheduler_from_request_start(self) -> None:
        sched = FiveMinuteTTLScheduler(default_ttl_seconds=300.0, warning_lead_seconds=45.0)
        # Request starts at t=1000.0 with 120,000 cached tokens; streaming takes 240s (finishes at t=1240.0)
        sched.record_request_start("sess_1", cached_prefix_tokens=120_000, now_ts=1000.0)
        sched.record_response_complete("sess_1", now_ts=1240.0)

        # At t=1265.0 (265s after request start -> only 35s left on 300s TTL!), must trigger PRE_EXPIRATION_WARNING
        rep = sched.inspect_session_ttl("sess_1", now_ts=1265.0)
        self.assertEqual(rep.state, "PRE_EXPIRATION_WARNING")
        self.assertEqual(rep.remaining_ttl_seconds, 35.0)
        self.assertTrue(rep.should_send_keepalive)
        self.assertLess(rep.estimated_keepalive_cost_usd, rep.estimated_cold_rewrite_cost_usd)

        # Trigger heartbeat ping and verify TTL resets to 300s
        pinged = sched.trigger_keepalive_heartbeat("sess_1", now_ts=1266.0)
        self.assertTrue(pinged)
        rep_after = sched.inspect_session_ttl("sess_1", now_ts=1270.0)
        self.assertEqual(rep_after.state, "HOT")
        self.assertAlmostEqual(rep_after.remaining_ttl_seconds, 296.0, places=1)

    def test_model_affinity_router_and_60_80_attention_governor(self) -> None:
        router = ModelAffinityRouter(primary_frontier_model="claude-opus-5-5", utility_haiku_model="claude-haiku-5-5")
        primary = router.route_primary_turn("claude-opus-5-5")
        self.assertEqual(primary.target_model, "claude-opus-5-5")

        # Switching primary model mid-session must raise ModelSwitchCacheViolationError
        with self.assertRaises(ModelSwitchCacheViolationError):
            router.route_primary_turn("claude-haiku-5-5")

        # Utility calls (session title & away summary) must route to isolated Haiku with thinking=disabled & skip_cache_write=True
        title_req = router.build_session_title_request("Architect and build cod.ai next-gen coding harness on Proxmox")
        self.assertEqual(title_req.model, "claude-haiku-5-5")
        self.assertEqual(title_req.thinking, {"type": "disabled"})
        self.assertTrue(title_req.skip_cache_write)
        title_words = title_req.parsed_result["title"].split()
        self.assertGreaterEqual(len(title_words), 3)
        self.assertLessEqual(len(title_words), 7)

        away_req = router.build_away_summary_request(
            [{"role": "user", "content": f"Turn {i}"} for i in range(45)]
        )
        self.assertEqual(away_req.parsed_result["messages_sampled"], 30)
        self.assertTrue(away_req.skip_cache_write)

        # Test 60-80% Attention Budget Governor
        gov = HybridContextGovernor(context_window=10_000, soft_ceiling_ratio=0.60, hard_ceiling_ratio=0.80)
        gov.index_file("src/context/cache_assembler.py", "cache_control ephemeral prefix " * 120)
        gov.index_file("src/security/proxy_sandbox.py", "bubblewrap re-firewall proxy " * 120)

        # Under 60% ceiling -> FULL_IN_CONTEXT_N2
        dec_full = gov.allocate_context_budget(current_Conversation_tokens=1_000, query="ephemeral prefix")
        self.assertEqual(dec_full.mode, "FULL_IN_CONTEXT_N2")
        self.assertEqual(len(dec_full.included_files), 2)

        # Above 60% ceiling -> HYBRID_PROJECT_KNOWLEDGE_SEARCH
        dec_search = gov.allocate_context_budget(current_Conversation_tokens=5_800, query="cache_assembler ephemeral")
        self.assertEqual(dec_search.mode, "HYBRID_PROJECT_KNOWLEDGE_SEARCH")
        self.assertEqual(dec_search.search_results[0]["filename"], "cache_assembler.py")
        self.assertLessEqual(dec_search.utilization_ratio, 0.80)


class TestPhase4MultiAgentFleetAndVerification(unittest.TestCase):
    def test_pi_session_dag_tree_branching_and_cache_meter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dag = PiSessionDAG(Path(tmpdir) / "session.jsonl")
            e1 = dag.append_node("system", "Static system prompt")
            e2 = dag.append_node("user", "Fix auth bug")
            e3 = dag.append_node("assistant", "Attempt v1 failed")
            # Rewind leaf back to e2 (/tree) and branch to e4 without deleting e3!
            dag.move_leaf_pointer(e2.id)
            e4 = dag.append_node("assistant", "Attempt v2 succeeded")

            active_ids = [n.id for n in dag.get_active_path()]
            self.assertEqual(active_ids, [e1.id, e2.id, e4.id])
            self.assertIn(e3.id, dag.nodes)  # e3 preserved in tree

            # Verify Cache Re-billed meter tracks unexpected miss but ignores intentional compaction
            dag.record_turn_usage(
                cache_read_tokens=0,
                cache_write_tokens=100_000,
                uncached_input_tokens=500,
                expected_cached_prefix_tokens=100_000,
                cause="cache miss after 12m idle",
                is_intentional_compaction=False,
            )
            self.assertEqual(dag.meter.cache_misses, 1)
            self.assertGreater(dag.meter.rebilled_cost_usd, 0.0)
            self.assertIn("Cache Re-billed:", dag.meter.format_pi_footer())

    def test_explore_subagent_triggers_above_3_queries_and_distills_1k_2k_brief(self) -> None:
        explore = ReadOnlyExploreSubAgent(WORKSPACE, trigger_threshold=3)
        queries = [
            DiscoveryQuery("Glob", "*.py", "src"),
            DiscoveryQuery("Grep", "cache_control", "src"),
            DiscoveryQuery("Grep", "ToolSearch", "src"),
            DiscoveryQuery("Read", "src/prompts/engine.py"),
        ]
        self.assertTrue(explore.should_spawn_explore_agent(queries))
        with self.assertRaises(ReadOnlyViolationError):
            explore.validate_tool_call("Write")

        brief = explore.execute_isolated_exploration("Map cod.ai core modules", queries)
        self.assertTrue(brief.within_budget_1k_to_2k, f"Brief tokens={brief.distilled_token_count} not in [1000, 2000]")
        self.assertGreaterEqual(brief.distilled_token_count, 1000)
        self.assertLessEqual(brief.distilled_token_count, 2000)

    def test_two_tier_compaction_stage1_cache_safe_and_stage2_9_sections(self) -> None:
        comp = TwoTierCompactionEngine()
        msgs = [
            {"role": "user", "content": [{"type": "tool_result", "content": "CACHED_PREFIX_OUTPUT_" * 40}]},
            {"role": "user", "content": [{"type": "tool_result", "content": "POST_BREAKPOINT_STALE_OUTPUT_" * 40}]},
            {"role": "user", "content": [{"type": "text", "text": "Recent turn 1"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "Recent turn 2"}]},
        ]
        # Index 0 is behind the cache breakpoint and MUST NOT be mutated! Index 1 is post-breakpoint and gets pruned.
        s1 = comp.run_stage1_micro_compaction(msgs, last_cached_message_index=0, keep_recent_turns=2)
        self.assertEqual(s1.pruned_tool_outputs_count, 1)
        self.assertNotIn("MICRO-COMPACTED", s1.messages[0]["content"][0]["content"])
        self.assertIn("MICRO-COMPACTED", s1.messages[1]["content"][0]["content"])

        # Stage 2: Verify NO_TOOLS_PREAMBLE blocks tool_use and strips <analysis> while keeping all 9 sections + top 5 files
        with self.assertRaises(CompactionValidationError):
            comp.parse_and_strip_analysis({"content": [{"type": "tool_use", "name": "Read"}]})

        recent_5 = [(f"src/mod_{i}.py", f"def func_{i}(): return {i}") for i in range(6)]
        s2 = comp.execute_stage2_compaction(
            layer2_message={"role": "user", "content": [{"type": "text", "text": "<project_static_context>CLAUDE.md</project_static_context>"}]},
            layer3_messages=msgs,
            recently_accessed_files=recent_5,
        )
        self.assertTrue(s2.all_9_sections_present)
        self.assertNotIn("<analysis>", s2.clean_summary_xml)
        self.assertEqual(len(s2.restored_top5_files), 5)

    def test_atomic_memory_concurrency_and_goal_worktree_coordinator(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = StructuredMemoryStore(Path(tmpdir) / "memory")
            st1 = mem.memory_write("ARCH.md", "Status: DRAFT\nModule: Core\n")
            self.assertEqual(st1.version, 1)

            # Wrong if_version must raise MemoryConcurrencyError
            with self.assertRaises(MemoryConcurrencyError):
                mem.memory_str_replace("ARCH.md", "Status: DRAFT", "Status: FINAL", if_version=99)

            # Ambiguous old_str (2 occurrences) must raise MemoryMatchError
            mem.memory_append("ARCH.md", "Status: DRAFT\n", if_version=1)
            with self.assertRaises(MemoryMatchError):
                mem.memory_str_replace("ARCH.md", "Status: DRAFT", "Status: FINAL", if_version=2)

            # Unique replacement with exact if_version=2 succeeds
            st3 = mem.memory_str_replace("ARCH.md", "Module: Core", "Module: VerifiedCore", if_version=2)
            self.assertEqual(st3.version, 3)

            # Test /goal Git Worktree Coordinator with 2 parallel worker branches
            repo_dir = Path(tmpdir) / "repo"
            wt_dir = Path(tmpdir) / "worktrees"
            repo_dir.mkdir()
            coord = GoalWorktreeCoordinator(repo_dir, wt_dir, mem)

            def worker_a(wt: Path, m: StructuredMemoryStore) -> str:
                (wt / "feature_a.py").write_text("FEATURE_A = True\n", encoding="utf-8")
                return "Implemented feature_a.py in isolated git worktree"

            def worker_b(wt: Path, m: StructuredMemoryStore) -> str:
                (wt / "feature_b.py").write_text("FEATURE_B = True\n", encoding="utf-8")
                return "Implemented feature_b.py in isolated git worktree"

            report = coord.execute_goal(
                "Build Parallel Features",
                [
                    GoalSubTask("task_a", "Feature A", "feat/branch-a", worker_a),
                    GoalSubTask("task_b", "Feature B", "feat/branch-b", worker_b),
                ],
            )
            self.assertTrue(report.all_succeeded)
            self.assertEqual(report.total_tasks, 2)
            goal_mem = mem.read_memory("GOAL_STATE.md")
            self.assertIn("Status: COMPLETED", goal_mem.content)

    def test_adversarial_verifier_permissions_and_spot_check(self) -> None:
        verifier = AdversarialVerificationAgent(WORKSPACE)
        self.assertTrue(verifier.should_trigger(files_edited_count=3))
        # Verifier must block project file writes with VerifierPermissionError (exit code 2)
        with self.assertRaises(VerifierPermissionError):
            verifier.guard_tool_invocation("Write", str(WORKSPACE / "src/hacked.py"))
        # Verifier must block spawning child agents
        with self.assertRaises(VerifierPermissionError):
            verifier.guard_tool_invocation("dispatch_specialist")
        # Verifier CAN write ephemeral test harness inside /tmp/
        tmp_harness = verifier.write_ephemeral_tmp_harness("cod_ai_verifier_probe.py", "print('EPHEMERAL_PROBE_OK')\n")
        self.assertTrue(tmp_harness.exists())


class TestPhase5ContainmentAndSecurityClassifier(unittest.TestCase):
    def test_credential_vault_proxy_and_sandbox_isolation(self) -> None:
        proxy = CredentialVaultProxy(
            credentials={"ANTHROPIC_API_KEY": "sk-ant-secret-key-999999", "HERETEK_LLM_KEY": "hk-secret-888888"}
        )
        runner = PluggableSandboxRunner(WORKSPACE, proxy)
        res = runner.execute_sandboxed(["python3", "-c", "import os; print('CONTAINED:', os.environ.get('COD_SANDBOX_CONTAINED'), 'KEY:', os.environ.get('ANTHROPIC_API_KEY'))"])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("CONTAINED: 1 KEY: None", res.stdout)
        self.assertFalse(res.credentials_exposed_in_env)

        # Outbound request to allowlisted api.anthropic.com injects x-api-key at boundary
        allowed_req = proxy.inspect_and_inject_outbound_request("https://api.anthropic.com/v1/messages", body='{"model": "claude-opus-5-5"}')
        self.assertTrue(allowed_req.allowed)
        self.assertTrue(allowed_req.injected_auth_header)
        self.assertEqual(allowed_req.sanitized_headers["x-api-key"], "sk-ant-secret-key-999999")

        # Outbound request to non-allowlisted domain is blocked (re-firewall quarantine)
        blocked_host = proxy.inspect_and_inject_outbound_request("https://evil.example.com/steal")
        self.assertFalse(blocked_host.allowed)

        # Outbound request attempting to exfiltrate raw key in payload is blocked
        exfil = proxy.inspect_and_inject_outbound_request("https://api.anthropic.com/v1/messages", body="Here is sk-ant-secret-key-999999")
        self.assertFalse(exfil.allowed)
        self.assertTrue(exfil.blocked_exfiltration)

    def test_2_stage_security_classifier_and_critique(self) -> None:
        clf = TwoStageSecurityClassifier()
        # Stage 1 fast allow
        v_allow = clf.evaluate_command("git status && pytest tests/")
        self.assertEqual(v_allow.decision, "ALLOW")
        self.assertEqual(v_allow.stage_reached, 1)
        self.assertEqual(v_allow.exit_code, 0)

        # Pipe with destructive subcommand -> Stage 1 SOFT_DENY (exit code 2)
        v_deny = clf.evaluate_command("git status | rm -rf /")
        self.assertEqual(v_deny.decision, "SOFT_DENY")
        self.assertEqual(v_deny.exit_code, 2)

        # Stage 2 escalation on high-blast-radius command (`re-firewall unmask`)
        v_stage2 = clf.evaluate_command("re-firewall unmask")
        self.assertEqual(v_stage2.decision, "ESCALATED_DENY")
        self.assertEqual(v_stage2.stage_reached, 2)
        self.assertEqual(v_stage2.exit_code, 2)
        self.assertIn("<stage2_security_thinking>", v_stage2.stage2_thinking_trace or "")

        # Critique utility detects overbroad and conflicting rules
        flawed_policy = SecurityPolicyConfig(
            allow_rules=[".*", "git push --force"],
            soft_deny_rules=["git push --force"],
        )
        crit = clf.critique_permission_rules(flawed_policy)
        self.assertEqual(crit.overall_health, "NEEDS_REVISION")
        self.assertGreaterEqual(len(crit.findings), 2)

    def test_skill_doctor_telemetry_dashboard(self) -> None:
        doc = SkillDoctorTelemetryEngine()
        snap = doc.run_skill_doctor(
            session_id="test_sess",
            model="claude-opus-5-5",
            active_tokens=150_000,
            context_window=1_000_000,
            cache_read_tokens=450_000,
            cache_write_tokens=50_000,
            cache_rebilled_usd=0.0,
            tokens_before_compact=600_000,
            tokens_after_compact=150_000,
            retrieved_items=["a.py", "b.py"],
            relevant_items={"a.py", "b.py"},
        )
        self.assertEqual(snap.context_utilization_pct, 15.0)
        self.assertEqual(snap.retrieval_precision_pct, 100.0)
        md = snap.render_dashboard_markdown()
        self.assertIn("`/skill doctor`", md)



    def test_phase6_claude_web_opus_5_5_gui_and_endpoint_studio(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("web_server", str(WORKSPACE / "src" / "web_server.py"))
        ws = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ws)
        EndpointConfigPayload, ChatTurnPayload, configure_custom_endpoint, assemble_three_layer_turn = ws.EndpointConfigPayload, ws.ChatTurnPayload, ws.configure_custom_endpoint, ws.assemble_three_layer_turn
        import json
        gui_path = WORKSPACE / "web" / "index.html"
        self.assertTrue(gui_path.exists())
        html = gui_path.read_text(encoding="utf-8")
        # Verify Claude Web Opus 5.5 design tokens & controls
        for token in ["#faf9f5", "#181715", "#cc785c", "claude-opus-5-5", "modal-endpoint-studio", "select-effort", "select-thinking-display"]:
            self.assertIn(token, html)

        # Verify custom endpoint configuration API
        ep_resp = configure_custom_endpoint(EndpointConfigPayload(
            base_url="https://llm.heretek.one/v1/messages",
            wire_protocol="anthropic-messages",
            model="claude-opus-5-5",
            api_key="hk-test-key-123456789",
        ))
        ep_data = json.loads(ep_resp.body.decode("utf-8"))
        self.assertTrue(ep_data["allowlisted"])
        self.assertTrue(ep_data["vault_sealed"])

        # Verify 3-layer chat turn assembly via web server
        turn_resp = assemble_three_layer_turn(ChatTurnPayload(
            prompt="Architect a new microservice",
            model="claude-opus-5-5",
            effort="xhigh",
            thinking_display="summarized",
        ))
        turn_data = json.loads(turn_resp.body.decode("utf-8"))
        self.assertEqual(turn_data["output_config"]["effort"], "xhigh")
        self.assertEqual(turn_data["thinking"]["type"], "adaptive")


if __name__ == "__main__":
    unittest.main(verbosity=2)
