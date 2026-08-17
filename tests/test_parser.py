import json
import tempfile
import unittest
from pathlib import Path

from codex_runtime_hud import IncrementalReaderPool, IncrementalRolloutReader, RolloutCandidate, RootThreadSelector, SessionSelection, parse_rollout, resolve_language

ROWS = [{'timestamp': '2026-08-14T00:00:00Z', 'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': 't1', 'started_at': 1786665600, 'model_context_window': 200000}}, {'timestamp': '2026-08-14T00:00:00.1Z', 'type': 'event_msg', 'payload': {'type': 'thread_settings_applied', 'thread_settings': {'model': 'gpt-5.6-luna'}}}, {'timestamp': '2026-08-14T00:00:03Z', 'type': 'event_msg', 'payload': {'type': 'raw_response_completed', 'response_id': 'r1', 'token_usage': {'input_tokens': 100000, 'cached_input_tokens': 95000, 'cache_write_input_tokens': 0, 'output_tokens': 5000, 'reasoning_output_tokens': 1000, 'total_tokens': 106000}}}, {'timestamp': '2026-08-14T00:00:10Z', 'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {'total_token_usage': {'input_tokens': 100000, 'cached_input_tokens': 95000, 'cache_write_input_tokens': 0, 'output_tokens': 5000, 'reasoning_output_tokens': 1000, 'total_tokens': 106000}, 'last_token_usage': {'input_tokens': 100000, 'cached_input_tokens': 95000, 'cache_write_input_tokens': 0, 'output_tokens': 5000, 'reasoning_output_tokens': 1000, 'total_tokens': 106000}, 'model_context_window': 200000}, 'rate_limits': None}}, {'timestamp': '2026-08-14T00:00:10Z', 'type': 'event_msg', 'payload': {'type': 'task_complete', 'turn_id': 't1', 'started_at': 1786665600, 'completed_at': 1786665610, 'duration_ms': 10000, 'time_to_first_token_ms': 900, 'last_agent_message': 'done'}}, {'timestamp': '2026-08-14T00:01:00Z', 'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': 't2', 'started_at': 1786665660, 'model_context_window': 200000}}, {'timestamp': '2026-08-14T00:01:02Z', 'type': 'event_msg', 'payload': {'type': 'exec_command_begin', 'call_id': 'c1', 'turn_id': 't2', 'started_at_ms': 1786665662000, 'command': ['git', 'status'], 'cwd': '.'}}, {'timestamp': '2026-08-14T00:01:03Z', 'type': 'event_msg', 'payload': {'type': 'mcp_tool_call_begin', 'call_id': 'c2', 'turn_id': 't2', 'invocation': {'server': 'x', 'tool': 'read', 'arguments': {}}}}, {'timestamp': '2026-08-14T00:01:05Z', 'type': 'event_msg', 'payload': {'type': 'exec_command_end', 'call_id': 'c1', 'turn_id': 't2', 'completed_at_ms': 1786665665000, 'command': ['git', 'status'], 'cwd': '.'}}, {'timestamp': '2026-08-14T00:01:07Z', 'type': 'event_msg', 'payload': {'type': 'mcp_tool_call_end', 'call_id': 'c2', 'turn_id': 't2', 'duration': '4s', 'result': {'Ok': {}}}}, {'timestamp': '2026-08-14T00:01:15Z', 'type': 'event_msg', 'payload': {'type': 'raw_response_completed', 'response_id': 'r2', 'token_usage': {'input_tokens': 20000, 'cached_input_tokens': 18000, 'cache_write_input_tokens': 0, 'output_tokens': 2000, 'reasoning_output_tokens': 300, 'total_tokens': 22300}}}, {'timestamp': '2026-08-14T00:01:20Z', 'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {'total_token_usage': {'input_tokens': 120000, 'cached_input_tokens': 113000, 'cache_write_input_tokens': 0, 'output_tokens': 7000, 'reasoning_output_tokens': 1300, 'total_tokens': 128300}, 'last_token_usage': {'input_tokens': 20000, 'cached_input_tokens': 18000, 'cache_write_input_tokens': 0, 'output_tokens': 2000, 'reasoning_output_tokens': 300, 'total_tokens': 22300}, 'model_context_window': 200000}, 'rate_limits': None}}, {'timestamp': '2026-08-14T00:01:20Z', 'type': 'event_msg', 'payload': {'type': 'task_complete', 'turn_id': 't2', 'started_at': 1786665660, 'completed_at': 1786665680, 'duration_ms': 20000, 'time_to_first_token_ms': 800, 'last_agent_message': 'done'}}]

class HudTests(unittest.TestCase):
    def test_latest_turn_scope_and_task_aliases(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "rollout-test.jsonl"
            p.write_text("\n".join(json.dumps(x) for x in ROWS), encoding="utf-8")
            parsed = parse_rollout(p)

            turn = parsed.metrics("turn")
            self.assertEqual(turn.model, "gpt-5.6-luna")
            self.assertEqual(turn.rounds, 1)
            self.assertEqual(turn.steps, 2)
            self.assertEqual(turn.usage.input_tokens, 20000)
            self.assertEqual(turn.usage.cached_input_tokens, 18000)
            self.assertEqual(turn.usage.output_tokens, 2000)
            self.assertAlmostEqual(turn.usage.cache_hit, 90.0, places=1)
            self.assertAlmostEqual(turn.wall_seconds, 20.0, places=2)
            # Tool intervals: exec [2,5], MCP [3,7] => union [2,7] = 5s
            self.assertAlmostEqual(turn.tool_seconds, 5.0, places=2)
            self.assertAlmostEqual(turn.llm_seconds_est, 15.0, places=2)
            self.assertEqual(turn.ttft_avg_ms, 800)

            session = parsed.metrics("session")
            self.assertEqual(session.rounds, 2)
            self.assertEqual(session.steps, 2)
            self.assertEqual(session.usage.input_tokens, 120000)
            self.assertEqual(session.usage.output_tokens, 7000)

    def test_current_turn_falls_back_to_cumulative_delta(self):
        rows = [
            {"timestamp":"2026-08-14T00:00:00Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":1000,"cached_input_tokens":800,"output_tokens":100,"reasoning_output_tokens":0,"total_tokens":1100},"last_token_usage":{"input_tokens":1000,"cached_input_tokens":800,"output_tokens":100,"reasoning_output_tokens":0,"total_tokens":1100},"model_context_window":10000},"rate_limits":None}},
            {"timestamp":"2026-08-14T00:00:01Z","type":"event_msg","payload":{"type":"task_started","turn_id":"x","started_at":1786665601,"model_context_window":10000}},
            {"timestamp":"2026-08-14T00:00:04Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":1500,"cached_input_tokens":1200,"output_tokens":180,"reasoning_output_tokens":0,"total_tokens":1680},"last_token_usage":{"input_tokens":500,"cached_input_tokens":400,"output_tokens":80,"reasoning_output_tokens":0,"total_tokens":580},"model_context_window":10000},"rate_limits":None}},
            {"timestamp":"2026-08-14T00:00:05Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"x","started_at":1786665601,"completed_at":1786665605,"duration_ms":4000,"time_to_first_token_ms":500}},
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "rollout-fallback.jsonl"
            p.write_text("\n".join(json.dumps(x) for x in rows), encoding="utf-8")
            m = parse_rollout(p).metrics("turn")
            self.assertEqual(m.usage.input_tokens, 500)
            self.assertEqual(m.usage.cached_input_tokens, 400)
            self.assertEqual(m.usage.output_tokens, 80)

    def test_incremental_reader_matches_full_parse_and_handles_partial_line(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "rollout-incremental.jsonl"
            first = "\n".join(json.dumps(x) for x in ROWS[:5]) + "\n"
            p.write_text(first, encoding="utf-8")
            reader = IncrementalRolloutReader()
            initial = reader.read(p)
            self.assertEqual(initial.metrics("session").rounds, 1)
            with p.open("ab") as f:
                f.write(json.dumps(ROWS[5]).encode("utf-8"))
            partial = reader.read(p)
            self.assertEqual(partial.metrics("session").rounds, 1)
            with p.open("ab") as f:
                f.write(b"\n" + json.dumps(ROWS[6]).encode("utf-8") + b"\n")
            updated = reader.read(p)
            self.assertEqual(updated.metrics("session").rounds, 2)
            self.assertEqual(updated.metrics("turn").steps, 1)
            full = parse_rollout(p)
            self.assertEqual(updated.metrics("session").usage.output_tokens, full.metrics("session").usage.output_tokens)

    def test_incremental_reader_resets_on_truncate_and_counts_complete_invalid_line(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "rollout-reset.jsonl"
            p.write_text(json.dumps(ROWS[0]) + "\n", encoding="utf-8")
            reader = IncrementalRolloutReader()
            reader.read(p)
            with p.open("a", encoding="utf-8") as f:
                f.write("not-json\n")
            bad = reader.read(p)
            self.assertEqual(bad.parse_errors, 1)
            p.write_text(json.dumps(ROWS[5]) + "\n", encoding="utf-8")
            reset = reader.read(p)
            self.assertEqual(reset.parse_errors, 0)
            self.assertEqual(reset.metrics("session").rounds, 1)

    def test_language_resolution(self):
        self.assertEqual(resolve_language("zh-CN"), "zh-CN")
        self.assertEqual(resolve_language("en"), "en")
        self.assertIn(resolve_language("auto"), {"zh-CN", "en"})

    def test_response_item_call_output_is_one_timed_tool(self):
        rows = [
            {"timestamp": 1000, "type": "event_msg", "payload": {"type": "task_started", "turn_id": "r", "started_at": 1000}},
            {"timestamp": 1001, "type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "c1", "name": "exec"}},
            {"timestamp": 1005, "type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "c1", "output": "ok"}},
            {"timestamp": 1006, "type": "event_msg", "payload": {"type": "task_complete", "turn_id": "r", "completed_at": 1006}},
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "response-items.jsonl"
            p.write_text("\n".join(json.dumps(x) for x in rows), encoding="utf-8")
            m = parse_rollout(p).metrics("turn")
            self.assertEqual(m.steps, 1)
            self.assertAlmostEqual(m.tool_seconds, 4.0, places=3)
            self.assertAlmostEqual(m.tool_timing_coverage, 1.0, places=3)

    def test_mixed_wire_shapes_deduplicate_same_call(self):
        rows = [
            {"timestamp": 1000, "type": "event_msg", "payload": {"type": "task_started", "turn_id": "mix", "started_at": 1000}},
            {"timestamp": 1001, "type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "same", "name": "exec"}},
            {"timestamp": 1001, "type": "event_msg", "payload": {"type": "exec_command_begin", "call_id": "same", "turn_id": "mix", "started_at_ms": 1001000}},
            {"timestamp": 1005, "type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "same", "output": "ok"}},
            {"timestamp": 1005, "type": "event_msg", "payload": {"type": "exec_command_end", "call_id": "same", "turn_id": "mix", "completed_at_ms": 1005000}},
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "mixed-wire.jsonl"
            p.write_text("\n".join(json.dumps(x) for x in rows), encoding="utf-8")
            m = parse_rollout(p).metrics("turn")
            self.assertEqual(m.steps, 1)
            self.assertAlmostEqual(m.tool_seconds, 4.0, places=3)

    def test_canonical_item_wrappers_map_tools_and_ignore_plan(self):
        rows = [
            {"timestamp": 1000, "type": "event_msg", "payload": {"type": "task_started", "turn_id": "c", "started_at": 1000}},
            {"type": "event_msg", "payload": {"type": "item_started", "turn_id": "c", "started_at_ms": 1000000, "item": {"type": "CommandExecution", "id": "cmd"}}},
            {"type": "event_msg", "payload": {"type": "item_completed", "turn_id": "c", "completed_at_ms": 1004000, "item": {"type": "CommandExecution", "id": "cmd"}}},
            {"type": "event_msg", "payload": {"type": "item_started", "turn_id": "c", "started_at_ms": 1005000, "item": {"type": "McpToolCall", "id": "mcp"}}},
            {"type": "event_msg", "payload": {"type": "item_completed", "turn_id": "c", "completed_at_ms": 1007000, "item": {"type": "McpToolCall", "id": "mcp"}}},
            {"type": "event_msg", "payload": {"type": "item_completed", "turn_id": "c", "completed_at_ms": 1008000, "item": {"type": "Plan", "id": "plan"}}},
            {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "c", "completed_at": 1009}},
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "canonical-items.jsonl"
            p.write_text("\n".join(json.dumps(x) for x in rows), encoding="utf-8")
            m = parse_rollout(p).metrics("turn")
            self.assertEqual(m.steps, 2)
            self.assertAlmostEqual(m.tool_seconds, 6.0, places=3)

    def test_raw_response_usage_is_deduplicated_and_pending_is_visible(self):
        rows = [
            {"timestamp": 1000, "type": "event_msg", "payload": {"type": "task_started", "turn_id": "u", "started_at": 1000}},
            {"timestamp": 1001, "type": "event_msg", "payload": {"type": "raw_response_completed", "response_id": "same", "token_usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}}},
            {"timestamp": 1002, "type": "event_msg", "payload": {"type": "raw_response_completed", "response_id": "same", "token_usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}}},
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "raw-dedup.jsonl"
            p.write_text("\n".join(json.dumps(x) for x in rows), encoding="utf-8")
            m = parse_rollout(p).metrics("turn")
            self.assertEqual(m.exact_response_count, 1)
            self.assertEqual(m.usage.output_tokens, 2)
            p.write_text(json.dumps(rows[0]), encoding="utf-8")
            pending = parse_rollout(p).metrics("turn")
            self.assertTrue(pending.usage_pending)

    def test_selector_excludes_subagent_and_follows_new_root_task(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sessions = home / "sessions"; sessions.mkdir()
            def write(name, source, started):
                p = sessions / name; p.write_text("\n".join([
                    json.dumps({"type": "session_meta", "payload": {"thread_source": source, "originator": "Codex Desktop", "session_id": name}}),
                    json.dumps({"type": "event_msg", "payload": {"type": "task_started", "turn_id": name, "started_at": started}}),
                ]), encoding="utf-8"); return p
            root_old = write("rollout-root-old.jsonl", "user", 100)
            subagent = write("rollout-subagent.jsonl", "subagent", 999)
            selector = RootThreadSelector()
            self.assertEqual(selector.choose(home), root_old)
            root_new = write("rollout-root-new.jsonl", "user", 200)
            self.assertEqual(selector.choose(home), root_new)
            self.assertNotEqual(selector.choose(home), subagent)

    def test_selector_falls_back_to_archived_root(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td); (home / "sessions").mkdir(); archived = home / "archived_sessions"; archived.mkdir()
            p = archived / "rollout-archived-root.jsonl"
            p.write_text("\n".join([
                json.dumps({"type": "session_meta", "payload": {"thread_source": "user", "originator": "Codex Desktop"}}),
                json.dumps({"type": "event_msg", "payload": {"type": "task_started", "started_at": 100}}),
            ]), encoding="utf-8")
            self.assertEqual(RootThreadSelector().choose(home), p)

    def test_selector_scans_task_started_in_middle_of_large_rollout(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sessions = home / "sessions"
            sessions.mkdir()

            stale = sessions / "rollout-stale.jsonl"
            stale.write_text("\n".join([
                json.dumps({"type": "session_meta", "payload": {"thread_source": "user", "originator": "Codex Desktop"}}),
                json.dumps({"type": "event_msg", "payload": {"type": "task_started", "started_at": 200}}),
            ]), encoding="utf-8")

            large = sessions / "rollout-large.jsonl"
            with large.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps({"type": "session_meta", "payload": {"thread_source": "user", "originator": "Codex Desktop"}}) + "\n")
                handle.write(json.dumps({"type": "event_msg", "payload": {"type": "task_started", "started_at": 100}}) + "\n")
                handle.writelines(json.dumps({"type": "message", "payload": {"text": "x" * 240}}) + "\n" for _ in range(500))
                # This turn is deliberately outside the old head/tail sample.
                handle.write(json.dumps({"type": "event_msg", "payload": {"type": "task_started", "started_at": 300}}) + "\n")
                handle.writelines(json.dumps({"type": "message", "payload": {"text": "y" * 240}}) + "\n" for _ in range(700))

            selector = RootThreadSelector()
            self.assertEqual(selector.choose(home), large)
            candidate = next(item for item in selector.candidates(home) if item.path == large)
            self.assertEqual(candidate.task_started_ts, 300)

    def test_selector_metadata_cache_reads_appended_turn(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sessions = home / "sessions"
            sessions.mkdir()
            path = sessions / "rollout-live.jsonl"
            path.write_text("\n".join([
                json.dumps({"type": "session_meta", "payload": {"thread_source": "user", "originator": "Codex Desktop"}}),
                json.dumps({"type": "event_msg", "payload": {"type": "task_started", "started_at": 100}}),
            ]) + "\n", encoding="utf-8")

            selector = RootThreadSelector()
            self.assertEqual(selector.choose(home), path)
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps({"type": "event_msg", "payload": {"type": "task_started", "started_at": 200}}) + "\n")
            candidate = next(item for item in selector.candidates(home) if item.path == path)
            self.assertEqual(candidate.task_started_ts, 200)

    def test_session_selection_manual_lock_and_auto_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sessions = home / "sessions"
            sessions.mkdir()

            def write(name, project, started):
                path = sessions / name
                path.write_text("\n".join([
                    json.dumps({"type": "session_meta", "payload": {
                        "thread_source": "user", "originator": "Codex Desktop", "id": name.removeprefix("rollout-").removesuffix(".jsonl"),
                        "cwd": f"C:/work/{project}",
                    }}),
                    json.dumps({"type": "event_msg", "payload": {"type": "task_started", "started_at": started}}),
                ]) + "\n", encoding="utf-8")
                return path

            old_path = write("rollout-old-thread-1234.jsonl", "old-project", 100)
            new_path = write("rollout-new-thread-5678.jsonl", "new-project", 200)
            selection = SessionSelection()
            automatic = selection.resolve(home)
            self.assertEqual(automatic.candidate.path, new_path)
            old = next(candidate for candidate in automatic.candidates if candidate.path == old_path)
            self.assertEqual(old.display_name(), "old-project · old-thre")

            manual = selection.resolve(home, "manual", old.key)
            self.assertEqual(manual.mode, "manual")
            self.assertEqual(manual.candidate.path, old_path)
            write("rollout-newest-thread-9999.jsonl", "newest-project", 300)
            self.assertEqual(selection.resolve(home, "manual", old.key).candidate.path, old_path)
            self.assertEqual(selection.resolve(home).candidate.path.name, "rollout-newest-thread-9999.jsonl")

            old_path.unlink()
            fallback = selection.resolve(home, "manual", old.key)
            self.assertEqual(fallback.mode, "auto")
            self.assertEqual(fallback.candidate.path.name, "rollout-newest-thread-9999.jsonl")

    def test_candidate_activity_follows_turn_lifecycle_not_file_mtime(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sessions = home / "sessions"
            sessions.mkdir()
            path = sessions / "rollout-live.jsonl"
            path.write_text("\n".join([
                json.dumps({"type": "session_meta", "payload": {"thread_source": "user", "originator": "Codex Desktop"}}),
                json.dumps({"type": "event_msg", "payload": {"type": "task_started", "turn_id": "running", "started_at": 100}}),
            ]) + "\n", encoding="utf-8")
            selector = RootThreadSelector()
            candidate = selector.candidates(home)[0]
            self.assertTrue(candidate.is_active(now=999999))
            self.assertTrue(candidate.is_waiting_for_update(now=candidate.last_event_ts + 120))
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps({"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "running", "completed_at": 101}}) + "\n")
            candidate = selector.candidates(home)[0]
            self.assertFalse(candidate.is_active())

    def test_candidate_activity_priority_active_waiting_idle(self):
        active = RolloutCandidate(Path("active"), open_turn_ids={"turn"}, last_event_ts=100)
        waiting = RolloutCandidate(Path("waiting"), open_turn_ids={"turn"}, last_event_ts=100)
        idle = RolloutCandidate(Path("idle"), last_event_ts=100)
        self.assertEqual(active.activity_priority(now=110), 2)
        self.assertEqual(waiting.activity_priority(now=220), 1)
        self.assertEqual(idle.activity_priority(now=220), 0)

    def test_incremental_reader_pool_keeps_rollout_state_isolated(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            first = base / "rollout-first.jsonl"
            second = base / "rollout-second.jsonl"
            def rows(turn_id, response_id, output_tokens):
                return [
                    {"timestamp": 1000, "type": "event_msg", "payload": {"type": "task_started", "turn_id": turn_id, "started_at": 1000}},
                    {"timestamp": 1001, "type": "event_msg", "payload": {"type": "raw_response_completed", "response_id": response_id, "token_usage": {"input_tokens": 10, "output_tokens": output_tokens, "total_tokens": 10 + output_tokens}}},
                    {"timestamp": 1002, "type": "event_msg", "payload": {"type": "task_complete", "turn_id": turn_id, "completed_at": 1002}},
                ]
            first.write_text("\n".join(json.dumps(row) for row in rows("first", "first-response", 5)) + "\n", encoding="utf-8")
            second.write_text("\n".join(json.dumps(row) for row in rows("second", "second-response", 2)) + "\n", encoding="utf-8")
            readers = IncrementalReaderPool(max_readers=2)
            self.assertEqual(readers.read(first).metrics("turn").usage.output_tokens, 5)
            self.assertEqual(readers.read(second).metrics("turn").usage.output_tokens, 2)
            self.assertEqual(readers.read(first).metrics("turn").usage.output_tokens, 5)
            self.assertEqual(readers.read(second).metrics("turn").usage.output_tokens, 2)

if __name__ == "__main__":
    unittest.main()
