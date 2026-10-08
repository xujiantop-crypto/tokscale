import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

BASE = "d4d1c751856e25913bce97bfbd7b254308863239"
PRODUCT_PATHS = [
    "crates/tokscale-core/src/lib.rs",
    "crates/tokscale-core/src/sessions/codex.rs",
    "crates/tokscale-core/src/message_cache.rs",
    "crates/tokscale-cli/tests/cli_tests.rs",
    "crates/tokscale-core/src/tui_signal.rs",
]
OUT = Path("codex-source-validation")
OUT.mkdir(exist_ok=True)
MARKER = "source-completeness diagnostic"


def run(name, command, expect_success=True):
    result = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace")
    (OUT / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
    print(name, "exit", result.returncode, flush=True)
    print((result.stdout + result.stderr)[-2000:], flush=True)
    if expect_success:
        assert result.returncode == 0, name
    return result


def rows(*values):
    return "".join(json.dumps(value) + "\n" for value in values)


ACTIVITY = {"type": "response_item", "timestamp": "2020-01-01T00:00:00Z", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "done"}]}}
MODEL = {"type": "turn_context", "payload": {"model": "gpt-5.4"}}
USAGE = {"type": "event_msg", "timestamp": "2026-05-30T12:00:00Z", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 10}}}}
ZERO = {"type": "event_msg", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 0, "output_tokens": 0}}}}
HEADLESS_ACTIVITY = {"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}
HEADLESS_ZERO = {"type": "turn.completed", "usage": {"input_tokens": 0, "output_tokens": 0}}
HEADLESS_USAGE = {"type": "turn.completed", "timestamp": "2026-05-30T12:00:00Z", "model": "gpt-5.4", "usage": {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 10}}
CHILD = {"type": "session_meta", "payload": {"id": "019a0000-0002-7000-8000-000000000002", "forked_from_id": "019a0000-0001-7000-8000-000000000001", "thread_source": "user"}}
PARENT = {"type": "session_meta", "payload": {"id": "019a0000-0001-7000-8000-000000000001"}}
PARENT_TURN = {"type": "turn_context", "payload": {"turn_id": "019a0000-0001-7000-8000-000000000003", "model": "gpt-5.4"}}


def cli_controls(phase):
    binary = Path("target/debug/tokscale" + (".exe" if os.name == "nt" else "")).resolve()
    result = {}
    cases = {
        "native-unmetered": (rows(ACTIVITY), True, False),
        "headless-unmetered": (rows(HEADLESS_ACTIVITY), True, False),
        "native-zero": (rows(ACTIVITY, ZERO), False, False),
        "headless-zero": (rows(HEADLESS_ACTIVITY, HEADLESS_ZERO), False, False),
        "empty": ("", False, False),
        "metadata": (rows({"type": "session_meta", "payload": {"id": "empty"}}), False, False),
        "malformed": (rows(ACTIVITY) + "not json\n", False, False),
        "openclaw": (rows({"type": "session_meta", "payload": {"originator": "OpenClaw"}}, ACTIVITY), False, False),
        "inherited": (rows(CHILD, PARENT, PARENT_TURN, ACTIVITY), False, False),
        "fork-own-zero": (rows(CHILD, PARENT, PARENT_TURN, {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 100, "output_tokens": 20}}}}, {"type": "turn_context", "payload": {"turn_id": "019a0000-0002-7000-8000-000000000004", "model": "gpt-5.4"}}, ACTIVITY, {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 0, "output_tokens": 0}, "last_token_usage": {"input_tokens": 0, "output_tokens": 0}}}}), False, False),
        "native-metered": (rows(ACTIVITY, MODEL, USAGE), False, True),
        "headless-metered": (rows(HEADLESS_ACTIVITY, HEADLESS_USAGE), False, True),
        "malformed-metered": ("not json\n" + rows(ACTIVITY, MODEL, USAGE), False, True),
    }
    for kind in ["web_search_call", "tool_search_call", "tool_search_output", "image_generation_call"]:
        cases["native-" + kind] = (rows({"type": "response_item", "payload": {"type": kind}}), True, False)
    cases["synthetic-provider"] = (rows({"type": "session_meta", "payload": {"model_provider": "synthetic"}}, ACTIVITY), True, False, "synthetic")
    cases["synthetic-model"] = (rows({"type": "turn_context", "payload": {"model": "hf:example/model"}}, ACTIVITY), True, False, "synthetic")
    cases["synthetic-headless"] = (rows({"type": "item.completed", "model": "hf:example/model", "item": {"type": "agent_message", "text": "done"}}), True, False, "synthetic")
    cases["synthetic-openai-excluded"] = (rows(MODEL, ACTIVITY), False, False, "synthetic")
    for prefix in ["<environment_context>", "<system-reminder>", "<user_instructions>"]:
        cases["injected-" + prefix[1:-1]] = (rows({"type": "event_msg", "payload": {"type": "user_message", "message": prefix + "fixture context"}}), False, False)
    for name, case in cases.items():
        content, should_warn, metered = case[:3]
        client = case[3] if len(case) == 4 else "codex"
        home = (OUT / (phase + "-fixtures") / name).resolve()
        sessions = home / ".codex/sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        (sessions / "rollout.jsonl").write_text(content, encoding="utf-8", newline="\n")
        config = home / "config"
        cache = config / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        catalog = {"timestamp": int(time.time()), "data": {"gpt-5.4": {"input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6, "cache_read_input_token_cost": 1e-7}}}
        for filename in ["pricing-litellm.json", "pricing-openrouter.json", "pricing-models-dev.json"]:
            (cache / filename).write_text(json.dumps(catalog), encoding="utf-8")
        env = dict(os.environ, TOKSCALE_CONFIG_DIR=str(config), TOKSCALE_PRICING_CACHE_ONLY="1", HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9", ALL_PROXY="http://127.0.0.1:9")
        for key in ["CODEX_HOME", "TOKSCALE_EXTRA_DIRS", "TOKSCALE_HEADLESS_DIR"]:
            env.pop(key, None)
        for iteration in range(2):
            command = [str(binary), "--no-spinner", "monthly", "--json", "--client", client, "--home", str(home), "--since", "2026-05-01", "--until", "2026-05-31"]
            completed = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", env=env)
            assert completed.returncode == 0, completed.stderr
            report = json.loads(completed.stdout)
            (OUT / (phase + "-" + name + "-" + str(iteration) + "-stderr.log")).write_text(completed.stderr, encoding="utf-8")
            assert (MARKER in completed.stderr) == (phase == "fixed" and should_warn), (name, completed.stderr)
            if metered:
                entry = report["entries"][0]
                assert (entry["input"], entry["output"], entry["cacheRead"]) == (90, 20, 10), report
            else:
                assert report["entries"] == [] and report["totalCost"] == 0, report
            report.pop("processingTimeMs", None)
            result[name + "-" + str(iteration)] = {"stdout": report, "warning": MARKER in completed.stderr}
    task_cases = {
        "unmetered": (rows(ACTIVITY), True),
        "zero": (rows(ACTIVITY, ZERO), False),
        "injected": (rows({"type": "event_msg", "payload": {"type": "user_message", "message": "<environment_context>fixture context"}}), False),
        "metadata": (rows({"type": "session_meta", "payload": {"id": "empty"}}), False),
        "malformed": (rows(ACTIVITY) + "not json\n", False),
        "openclaw": (rows({"type": "session_meta", "payload": {"originator": "OpenClaw"}}, ACTIVITY), False),
        "inherited": (rows(CHILD, PARENT, PARENT_TURN, ACTIVITY), False),
    }
    for name, (content, should_warn) in task_cases.items():
        home = (OUT / (phase + "-task-fixtures") / name).resolve()
        sessions = home / ".codex/sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        (sessions / "rollout.jsonl").write_text(content, encoding="utf-8", newline="\n")
        config = home / "config"
        config.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, TOKSCALE_CONFIG_DIR=str(config), TOKSCALE_PRICING_CACHE_ONLY="1", HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9", ALL_PROXY="http://127.0.0.1:9")
        for key in ["CODEX_HOME", "TOKSCALE_EXTRA_DIRS", "TOKSCALE_HEADLESS_DIR"]:
            env.pop(key, None)
        for iteration in range(2):
            command = [str(binary), "--no-spinner", "report", "--no-summarize", "--json", "--home", str(home)]
            completed = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", env=env)
            assert completed.returncode == 0, completed.stderr
            report = json.loads(completed.stdout)
            assert report == [], report
            assert (MARKER in completed.stderr) == (phase == "fixed" and should_warn), (name, completed.stderr)
            (OUT / (phase + "-task-" + name + "-" + str(iteration) + "-stderr.log")).write_text(completed.stderr, encoding="utf-8")
            result["task-" + name + "-" + str(iteration)] = {"stdout": report, "warning": MARKER in completed.stderr}
    (OUT / (phase + "-cli.json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(phase, "CLI controls", len(result), flush=True)
    return result


mode = sys.argv[1]
if mode == "tui-baseline":
    fixed_source = {path: Path(path).read_bytes() for path in PRODUCT_PATHS}
    try:
        for path in PRODUCT_PATHS:
            original = subprocess.check_output(["git", "show", "003dd688480840dd024e42faa1b0b3f08998756e:" + path]).decode("utf-8")
            if path.endswith("/lib.rs"):
                source = Path(path).read_text(encoding="utf-8")
                start = source.index("    #[test]\n    #[serial]\n    fn missing_codex_usage_warning_coalesces_tui_refreshes_and_clears_resolved_sources()")
                marker = "    /// Re-aim a live"
                end = source.index(marker, start)
                original = original.replace(marker, source[start:end] + marker, 1)
            Path(path).write_text(original, encoding="utf-8", newline="\n")
        name = "missing_codex_usage_warning_coalesces_tui_refreshes_and_clears_resolved_sources"
        result = run("published-tui-regression", ["cargo", "test", "--locked", "-p", "tokscale-core", "--lib", name, "--", "--nocapture"], False)
        assert result.returncode != 0 and "test result: FAILED" in result.stdout
        assert any(name in line and "FAILED" in line for line in result.stdout.splitlines())
        assert "left: 3" in result.stderr and "right: 1" in result.stderr, result.stderr
    finally:
        for path, content in fixed_source.items():
            Path(path).write_bytes(content)
elif mode == "feedback-baseline":
    fixed_source = {path: Path(path).read_bytes() for path in PRODUCT_PATHS}
    try:
        for path in PRODUCT_PATHS:
            original = subprocess.check_output(["git", "show", "012f96da8c40c78c80ded4c0577991b323a85e28:" + path]).decode("utf-8")
            source = Path(path).read_text(encoding="utf-8")
            if path.endswith("/lib.rs"):
                start = source.index("    #[test]\n    #[serial]\n    fn missing_codex_usage_warning_tracks_synthetic_activity()")
                marker = "    /// Re-aim a live"
                end = source.index(marker, start)
                original = original.replace(marker, source[start:end] + marker, 1)
            elif path.endswith("/codex.rs"):
                start = source.index("    #[test]\n    fn missing_usage_recognizes_native_tool_items()")
                marker = "    #[test]\n    fn missing_usage_accepts_zero_native_and_headless_counters()"
                end = source.index(marker, start)
                original = original.replace(marker, source[start:end] + marker, 1)
            elif path.endswith("/cli_tests.rs"):
                start = source.index("#[test]\nfn missing_codex_usage_task_report_warns")
                marker = "#[test]\nfn test_monthly_v2_outputs"
                end = source.index(marker, start)
                original = original.replace(marker, source[start:end] + marker, 1)
            Path(path).write_text(original, encoding="utf-8", newline="\n")
        for name in ["missing_codex_usage_warning_tracks_synthetic_activity", "missing_codex_usage_warning_reaches_local_report_path", "missing_usage_recognizes_native_tool_items", "missing_usage_ignores_injected_user_context"]:
            result = run("published-" + name, ["cargo", "test", "--locked", "-p", "tokscale-core", "--lib", name, "--", "--nocapture"], False)
            assert result.returncode != 0 and "test result: FAILED" in result.stdout
            assert any(name in line and "FAILED" in line for line in result.stdout.splitlines())
        name = "missing_codex_usage_task_report_warns_and_excludes_injected_context"
        result = run("published-" + name, ["cargo", "test", "--locked", "-p", "tokscale-cli", "--test", "cli_tests", name, "--", "--nocapture"], False)
        assert result.returncode != 0 and "test result: FAILED" in result.stdout
        assert any(name in line and "FAILED" in line for line in result.stdout.splitlines())
    finally:
        for path, content in fixed_source.items():
            Path(path).write_bytes(content)
elif mode == "baseline":
    fixed = {path: Path(path).read_bytes() for path in PRODUCT_PATHS}
    try:
        for path in PRODUCT_PATHS:
            original = subprocess.check_output(["git", "show", BASE + ":" + path]).decode("utf-8")
            source = Path(path).read_text(encoding="utf-8")
            if path.endswith("/lib.rs"):
                start = source.index("    fn take_missing_codex_usage_warnings()")
                end = source.index("    /// Re-aim a live", start)
                original = original.replace("    /// Re-aim a live", source[start:end] + "    /// Re-aim a live", 1)
            elif path.endswith("/cli_tests.rs"):
                start = source.index("#[test]\nfn missing_codex_usage_cli_warns")
                end = source.index("#[test]\nfn test_monthly_v2_outputs", start)
                original = original.replace("#[test]\nfn test_monthly_v2_outputs", source[start:end] + "#[test]\nfn test_monthly_v2_outputs", 1)
            Path(path).write_text(original, encoding="utf-8", newline="\n")
        core = run("baseline-core", ["cargo", "test", "--locked", "-p", "tokscale-core", "--lib", "missing_codex_usage", "--", "--nocapture"], False)
        assert core.returncode != 0 and "test result: FAILED" in core.stdout
        for name in ["missing_codex_usage_warning_tracks_cold_warm_append_rewrite_and_deletion", "missing_codex_usage_warning_is_aggregate_and_independent_of_report_dates"]:
            assert any(name in line and "FAILED" in line for line in core.stdout.splitlines()), name
        cli = run("baseline-cli-tests", ["cargo", "test", "--locked", "-p", "tokscale-cli", "--test", "cli_tests", "missing_codex_usage", "--", "--nocapture"], False)
        assert cli.returncode != 0 and "test result: FAILED" in cli.stdout
        assert any("missing_codex_usage_cli_warns" in line and "FAILED" in line for line in cli.stdout.splitlines())
        cli_controls("baseline")
    finally:
        for path, content in fixed.items():
            Path(path).write_bytes(content)
elif mode in ("final", "windows-followthrough", "review-final"):
    run("format", ["cargo", "fmt", "--all", "--", "--check"])
    clippy_command = ["cargo", "clippy", "--locked", "--workspace", "--all-features", "--message-format=json", "--", "-D", "warnings"]
    if mode == "final" or (mode == "review-final" and os.name != "nt"):
        run("clippy", clippy_command)
    else:
        assert os.name == "nt"
        fixed_source = {path: Path(path).read_bytes() for path in PRODUCT_PATHS}
        fixed_lint = run("windows-fixed-clippy", clippy_command, False)
        try:
            for path in PRODUCT_PATHS:
                Path(path).write_bytes(subprocess.check_output(["git", "show", BASE + ":" + path]))
            base_lint = run("windows-base-clippy", clippy_command, False)
        finally:
            for path, content in fixed_source.items():
                Path(path).write_bytes(content)
        def diagnostics(result):
            messages = []
            for line in result.stdout.splitlines():
                record = json.loads(line)
                if record.get("reason") == "compiler-message" and record["message"]["level"] in ("error", "warning"):
                    message = record["message"]
                    message.pop("rendered", None)
                    messages.append(message)
            return sorted(messages, key=lambda value: json.dumps(value, sort_keys=True))
        fixed_diagnostics = diagnostics(fixed_lint)
        base_diagnostics = diagnostics(base_lint)
        assert fixed_lint.returncode == base_lint.returncode != 0
        assert fixed_diagnostics and fixed_diagnostics == base_diagnostics
        expected = {
            ("unused_imports", "crates/tokscale-cli/src/trae.rs", 58),
            ("dead_code", "crates/tokscale-cli/src/commands/usage/copilot.rs", 63),
            ("clippy::needless_return", "crates/tokscale-cli/src/antigravity.rs", 1102),
            ("clippy::needless_return", "crates/tokscale-cli/src/antigravity.rs", 1353),
            ("clippy::needless_return", "crates/tokscale-cli/src/commands/autosubmit.rs", 1454),
            ("clippy::needless_return", "crates/tokscale-cli/src/commands/autosubmit.rs", 1558),
        }
        observed = {(message["code"]["code"], span["file_name"].replace("\\", "/"), span["line_start"]) for message in fixed_diagnostics for span in message["spans"] if span["is_primary"]}
        assert len(fixed_diagnostics) == 6 and observed == expected, observed
        (OUT / "windows-clippy-baseline.json").write_text(json.dumps({"base": BASE, "fixed_exit": fixed_lint.returncode, "base_exit": base_lint.returncode, "comparison": "complete compiler-message objects excluding rendered text", "identical_diagnostics": fixed_diagnostics}, indent=2), encoding="utf-8")
        run("windows-core-clippy", ["cargo", "clippy", "--locked", "-p", "tokscale-core", "--all-features", "--", "-D", "warnings"])
    run("workspace-tests", ["cargo", "test", "--workspace", "--all-features"])
    run("build-cli", ["cargo", "build", "--locked", "-p", "tokscale-cli"])
    if mode == "review-final" and os.name != "nt":
        run("rustdoc", ["cargo", "doc", "--locked", "--no-deps", "--workspace"])
    fixed = cli_controls("fixed")
    baseline = json.loads((OUT / "baseline-cli.json").read_text(encoding="utf-8"))
    assert {key: value["stdout"] for key, value in fixed.items()} == {key: value["stdout"] for key, value in baseline.items()}
    hashes = {path: hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for path in PRODUCT_PATHS}
    counts = {"synthetic_cli_invocations": len(fixed) + len(baseline)} if mode != "windows-followthrough" else {"current_run_cli_invocations": len(fixed), "reused_baseline_cli_reports": len(baseline), "baseline_artifact_run_id": 37847250942}
    (OUT / "result.json").write_text(json.dumps({"base": BASE, "head": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip(), "required_gates": "passed" if (mode == "final" or os.name != "nt") else "Windows format/core Clippy/workspace tests/build passed; strict workspace Clippy has identical pinned-base failures", **counts, "stdout_equal_to_base": True, "source_hashes": hashes}, indent=2), encoding="utf-8")
else:
    raise ValueError(mode)
