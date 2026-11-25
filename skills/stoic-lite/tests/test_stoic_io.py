"""Unit tests for skills/stoic-lite/scripts/stoic_io.py (Python 3.10+ stdlib only)."""

from __future__ import annotations

from email.message import Message
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT_PATH = SCRIPT_DIR / "stoic_io.py"
SKILL_MD_PATH = Path(__file__).resolve().parents[1] / "SKILL.md"
sys.path.insert(0, str(SCRIPT_DIR))

import stoic_io  # noqa: E402


class FakeResponse:
    def __init__(self, payload: object, status: int = 200) -> None:
        self._raw = (
            payload.encode("utf-8")
            if isinstance(payload, str)
            else json.dumps(payload).encode("utf-8")
        )
        self.status = status

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class RecordingOpener:
    """In-memory urllib opener stub that records every outbound request."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, object]] = []

    def open(self, req, timeout=None):
        raw_body = req.data.decode("utf-8") if req.data else None
        self.requests.append(
            {
                "method": req.get_method(),
                "url": req.full_url,
                "headers": {k.lower(): v for k, v in req.header_items()},
                "body": json.loads(raw_body) if raw_body else None,
                "timeout": timeout,
            }
        )
        if not self._responses:
            raise AssertionError("Unexpected extra HTTP request")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def make_http_error(code: int, body: object, url: str = "https://tryblume.ai/api/test") -> HTTPError:
    raw = (
        body.encode("utf-8")
        if isinstance(body, str)
        else json.dumps(body).encode("utf-8")
    )
    return HTTPError(url, code, f"HTTP {code}", Message(), io.BytesIO(raw))


class SkillDocTests(unittest.TestCase):
    def test_skill_md_is_under_50_lines(self) -> None:
        lines = SKILL_MD_PATH.read_text(encoding="utf-8").splitlines()
        self.assertLess(len(lines), 50)
        text = "\n".join(lines)
        self.assertIn("stoic_io.py", text)
        self.assertIn("--dry-run", text)
        self.assertIn("actor: agent", text)


class AuthResolutionTests(unittest.TestCase):
    def test_precedence_env_over_file_over_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp) / "custom-token"
            token_file.write_text("file_secret_token\n", encoding="utf-8")
            env = {
                "STOIC_API_TOKEN": "  env_secret_token \n",
                "STOIC_API_TOKEN_FILE": str(token_file),
            }
            self.assertEqual(stoic_io.resolve_token(env), "env_secret_token")
            del env["STOIC_API_TOKEN"]
            self.assertEqual(stoic_io.resolve_token(env), "file_secret_token")

    def test_default_token_path_used_when_env_unset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            default_path = Path(tmp) / ".config" / "stoic" / "codex-token"
            default_path.parent.mkdir(parents=True)
            default_path.write_text("default_home_token\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"HOME": tmp}, clear=False):
                self.assertEqual(stoic_io.resolve_token({}), "default_home_token")

    def test_missing_empty_and_invalid_tokens_raise_auth_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-token"
            with self.assertRaises(stoic_io.StoicAuthError):
                stoic_io.resolve_token({"STOIC_API_TOKEN_FILE": str(missing)})

            empty = Path(tmp) / "empty-token"
            empty.write_text("   \n", encoding="utf-8")
            with self.assertRaises(stoic_io.StoicAuthError):
                stoic_io.resolve_token({"STOIC_API_TOKEN_FILE": str(empty)})

            bad_secret = "tok with spaces"
            with self.assertRaises(stoic_io.StoicAuthError) as ctx:
                stoic_io.resolve_token({"STOIC_API_TOKEN": bad_secret})
            self.assertNotIn(bad_secret, str(ctx.exception))


class TokenLeakAndSecurityTests(unittest.TestCase):
    def test_no_redirect_refuses_redirects(self) -> None:
        handler = stoic_io.NoRedirect()
        self.assertIsNone(
            handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example/")
        )

    def test_token_never_leaks_in_http_or_url_errors(self) -> None:
        secret = "stoic_super_secret_token_987654321"
        opener = RecordingOpener(
            [make_http_error(401, {"detail": f"bad bearer {secret}"})]
        )
        with self.assertRaises(stoic_io.StoicHTTPError) as ctx:
            stoic_io.api_request("GET", "/api/auth/web/me", secret, opener=opener)
        self.assertNotIn(secret, str(ctx.exception))
        self.assertIn("<redacted>", str(ctx.exception))

        opener2 = RecordingOpener([URLError(f"tunnel rejected {secret}")])
        with self.assertRaises(stoic_io.StoicError) as ctx2:
            stoic_io.api_request("GET", "/api/auth/web/me", secret, opener=opener2)
        self.assertNotIn(secret, str(ctx2.exception))
        self.assertIn("<redacted>", str(ctx2.exception))

    def test_dry_run_does_not_read_token_or_leak_secret(self) -> None:
        secret = "stoic_never_touch_me_token"
        env = {"STOIC_API_TOKEN": secret}
        opener = RecordingOpener([])  # Would fail if any HTTP request were made.
        cmd, data, _ = stoic_io.run_command(
            ["save-bookmark", "--url", "https://example.com/a", "--dry-run"],
            env=env,
            opener=opener,
        )
        self.assertEqual(cmd, "save-bookmark")
        self.assertEqual(opener.requests, [])
        serialized = json.dumps(data)
        self.assertNotIn(secret, serialized)
        self.assertEqual(data["headers"]["Authorization"], "Bearer <redacted>")

    def test_dry_run_works_without_any_credential_configured(self) -> None:
        env = {"STOIC_API_TOKEN_FILE": "/nonexistent/path/codex-token"}
        _, data, _ = stoic_io.run_command(
            ["save-note", "--title", "T", "--body", "B", "--dry-run"],
            env=env,
        )
        self.assertTrue(data["dry_run"])

    def test_write_aborts_when_actor_is_not_agent(self) -> None:
        env = {"STOIC_API_TOKEN": "tok_user_123"}
        opener = RecordingOpener(
            [FakeResponse({"id": "u1", "actor": "user", "account_type": "admin"})]
        )
        with self.assertRaises(stoic_io.StoicAuthError) as ctx:
            stoic_io.run_command(
                ["save-bookmark", "--url", "https://example.com"],
                env=env,
                opener=opener,
            )
        self.assertIn("expected 'agent'", str(ctx.exception))
        # Only GET /api/auth/web/me ran; POST /api/bookmarks was never sent.
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(opener.requests[0]["method"], "GET")
        self.assertTrue(str(opener.requests[0]["url"]).endswith("/api/auth/web/me"))


class ReadCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = {"STOIC_API_TOKEN": "tok_agent_abc"}

    def test_whoami_json_and_human(self) -> None:
        payload = {
            "id": "u42",
            "actor": "agent",
            "account_type": "admin",
            "auth_provider": "APPLE",
        }
        opener = RecordingOpener([FakeResponse(payload)])
        cmd, data, fmt = stoic_io.run_command(["whoami"], env=self.env, opener=opener)
        self.assertEqual((cmd, fmt), ("whoami", "json"))
        self.assertEqual(data, payload)
        self.assertEqual(
            opener.requests[0]["headers"]["authorization"], "Bearer tok_agent_abc"
        )
        human = stoic_io.format_human(cmd, data)
        self.assertIn("actor=agent", human)
        self.assertIn("id=u42", human)

    def test_search_builds_repeated_types_and_validates(self) -> None:
        opener = RecordingOpener(
            [
                FakeResponse(
                    {
                        "items": [
                            {
                                "type": "project",
                                "id": "p1",
                                "title": "Ribbon Field",
                                "snippet": "multi-agent workspace",
                            }
                        ]
                    }
                )
            ]
        )
        cmd, data, fmt = stoic_io.run_command(
            [
                "search",
                "Ribbon Field",
                "--types",
                "note,task",
                "--types",
                "project",
                "--limit",
                "3",
                "--mode",
                "hybrid" if False else "semantic",
                "--human",
            ],
            env=self.env,
            opener=opener,
        )
        self.assertEqual((cmd, fmt), ("search", "human"))
        parsed = urlsplit(str(opener.requests[0]["url"]))
        qs = parse_qs(parsed.query)
        self.assertEqual(parsed.path, "/api/search/records")
        self.assertEqual(qs["q"], ["Ribbon Field"])
        self.assertEqual(qs["types"], ["note", "task", "project"])
        self.assertEqual(qs["limit"], ["3"])
        self.assertEqual(qs["mode"], ["semantic"])
        self.assertIn("[project] p1 — Ribbon Field", stoic_io.format_human(cmd, data))

        with self.assertRaises(stoic_io.StoicValidationError):
            stoic_io.run_command(["search", "x", "--types", "bogus"], env=self.env)
        with self.assertRaises(stoic_io.StoicValidationError):
            stoic_io.run_command(["search", "x", "--limit", "51"], env=self.env)

    def test_get_record_path_and_validation(self) -> None:
        opener = RecordingOpener(
            [FakeResponse({"type": "note", "id": "n1", "details": {"title": "Hi"}})]
        )
        cmd, data, _ = stoic_io.run_command(
            ["get", "note", "n1"], env=self.env, opener=opener
        )
        self.assertEqual(cmd, "get")
        self.assertEqual(data["id"], "n1")
        self.assertTrue(
            str(opener.requests[0]["url"]).endswith("/api/search/records/note/n1")
        )
        with self.assertRaises(stoic_io.StoicValidationError):
            stoic_io.run_command(["get", "invalid_type", "n1"], env=self.env)

    def test_list_tasks_status_all_vs_filtered(self) -> None:
        opener = RecordingOpener(
            [
                FakeResponse({"items": [], "total": 0}),
                FakeResponse(
                    {
                        "items": [{"id": "t1", "status": "pending", "title": "Ship"}],
                        "total": 1,
                    }
                ),
            ]
        )
        stoic_io.run_command(
            ["list-tasks", "--status", "all", "--limit", "5"],
            env=self.env,
            opener=opener,
        )
        qs_all = parse_qs(urlsplit(str(opener.requests[0]["url"])).query)
        self.assertNotIn("status", qs_all)
        self.assertEqual(qs_all["limit"], ["5"])

        cmd, data, _ = stoic_io.run_command(
            ["list-tasks", "--status", "pending", "--project-id", "proj9"],
            env=self.env,
            opener=opener,
        )
        qs_pending = parse_qs(urlsplit(str(opener.requests[1]["url"])).query)
        self.assertEqual(qs_pending["status"], ["pending"])
        self.assertEqual(qs_pending["project_id"], ["proj9"])
        self.assertIn("[pending] t1 — Ship", stoic_io.format_human(cmd, data))


class WriteCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = {"STOIC_API_TOKEN": "tok_agent_write"}
        self.me_ok = FakeResponse({"id": "u1", "actor": "agent", "account_type": "admin"})

    def test_save_note_body_and_stdin_dry_run_and_live(self) -> None:
        env = {**self.env, "AGENT_COORD_SESSION_ID": "sess-123"}
        _, dry, _ = stoic_io.run_command(
            [
                "save-note",
                "--title",
                "Architecture note",
                "--body-file",
                "-",
                "--tags",
                "infra, stoic",
                "--project-id",
                "p42",
                "--dry-run",
            ],
            env=env,
            stdin=io.StringIO("Line 1\nLine 2\n"),
        )
        self.assertTrue(dry["dry_run"])
        self.assertEqual(dry["method"], "POST")
        self.assertEqual(dry["url"], "https://tryblume.ai/api/notes")
        self.assertEqual(
            dry["body"],
            {
                "title": "Architecture note",
                "content": "Line 1\nLine 2\n",
                "author": "agent",
                "tags": ["infra", "stoic"],
                "project_id": "p42",
                "agent_provenance": {"session_id": "sess-123"},
            },
        )

        opener = RecordingOpener(
            [self.me_ok, FakeResponse({"id": "n99", "title": "Direct"}, status=201)]
        )
        cmd, res, _ = stoic_io.run_command(
            ["save-note", "--title", "Direct", "--body", "Hello"],
            env=self.env,
            opener=opener,
        )
        self.assertEqual(cmd, "save-note")
        self.assertEqual(res["id"], "n99")
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(opener.requests[0]["method"], "GET")
        self.assertEqual(opener.requests[1]["method"], "POST")
        self.assertEqual(
            opener.requests[1]["body"],
            {"title": "Direct", "content": "Hello", "author": "agent"},
        )

    def test_save_note_from_real_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "note.md"
            md.write_text("# Heading\nBody", encoding="utf-8")
            _, dry, _ = stoic_io.run_command(
                ["save-note", "--title", "From file", "--body-file", str(md), "--dry-run"],
                env={},
            )
            self.assertEqual(dry["body"]["content"], "# Heading\nBody")

    def test_save_task_project_query_param_and_agreement_schemas(self) -> None:
        _, dry, _ = stoic_io.run_command(
            [
                "save-task",
                "--title",
                "Audit compaction hooks",
                "--description",
                "Check PreCompact and SessionStart across providers.",
                "--project-id",
                "proj_rf",
                "--due",
                "2026-12-01T17:00:00Z",
                "--confirmed",
                "--responsibility",
                "user",
                "--source",
                "thread://abc123",
                "--dry-run",
            ],
            env={},
        )
        parsed = urlsplit(dry["url"])
        self.assertEqual(parsed.path, "/api/tasks")
        self.assertEqual(parse_qs(parsed.query), {"project_id": ["proj_rf"]})
        self.assertNotIn("project_id", dry["body"])
        self.assertEqual(
            dry["body"],
            {
                "title": "Audit compaction hooks",
                "description": "Check PreCompact and SessionStart across providers.",
                "status": "pending",
                "due_date": "2026-12-01T17:00:00Z",
                "agreement": {
                    "state": "confirmed",
                    "responsibility": "user",
                    "source": "thread://abc123",
                },
            },
        )

        # Suggested task with date-only --due and mocked live send
        opener = RecordingOpener(
            [self.me_ok, FakeResponse({"id": "t77", "title": "Try proxy"}, status=201)]
        )
        cmd, res, _ = stoic_io.run_command(
            [
                "save-task",
                "--title",
                "Try proxy",
                "--due",
                "2026-12-15",
                "--suggested",
                "--responsibility",
                "agent",
            ],
            env=self.env,
            opener=opener,
        )
        self.assertEqual(cmd, "save-task")
        self.assertEqual(res["id"], "t77")
        self.assertEqual(
            opener.requests[1]["body"]["agreement"],
            {"state": "suggested", "responsibility": "agent", "source": ""},
        )

        # Invalid --due fails locally
        with self.assertRaises(stoic_io.StoicValidationError):
            stoic_io.run_command(
                ["save-task", "--title", "Bad due", "--due", "next tuesday", "--dry-run"],
                env={},
            )

    def test_save_bookmark_dry_run_live_and_validation(self) -> None:
        _, dry, _ = stoic_io.run_command(
            [
                "save-bookmark",
                "--url",
                "https://example.com/post",
                "--title",
                "Good post",
                "--note",
                "Relevant to auth proxy",
                "--tags",
                "Security, Proxy, security",
                "--dry-run",
            ],
            env={},
        )
        self.assertEqual(dry["url"], "https://tryblume.ai/api/bookmarks")
        self.assertEqual(
            dry["body"],
            {
                "url": "https://example.com/post",
                "title": "Good post",
                "note": "Relevant to auth proxy",
                "tags": ["proxy", "security"],
            },
        )

        opener = RecordingOpener(
            [
                self.me_ok,
                FakeResponse(
                    {"id": "b1", "url": "https://example.com/post", "title": "Good post"},
                    status=201,
                ),
            ]
        )
        _, res, _ = stoic_io.run_command(
            ["save-bookmark", "--url", "https://example.com/post"],
            env=self.env,
            opener=opener,
        )
        self.assertEqual(res["id"], "b1")
        self.assertEqual(opener.requests[1]["body"], {"url": "https://example.com/post"})

        with self.assertRaises(stoic_io.StoicValidationError):
            stoic_io.run_command(
                ["save-bookmark", "--url", "ftp://example.com/file", "--dry-run"],
                env={},
            )


class HttpErrorAndSubprocessTests(unittest.TestCase):
    def test_http_error_surfaces_code_hint_and_detail(self) -> None:
        opener = RecordingOpener(
            [make_http_error(422, {"detail": [{"msg": "Field required"}]})]
        )
        with self.assertRaises(stoic_io.StoicHTTPError) as ctx:
            stoic_io.api_request("GET", "/api/tasks", "tok", opener=opener)
        self.assertEqual(ctx.exception.status, 422)
        self.assertIn("HTTP 422", str(ctx.exception))
        self.assertIn("Field required", str(ctx.exception))

    def test_subprocess_cli_dry_run_and_global_human_flag(self) -> None:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("STOIC_", "AGENT_COORD_", "CODEX_"))}
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "save-task",
                "--title",
                "Smoke check",
                "--confirmed",
                "--responsibility",
                "user",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        parsed = json.loads(proc.stdout)
        self.assertTrue(parsed["dry_run"])
        self.assertEqual(parsed["body"]["title"], "Smoke check")

        proc_human = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--human",
                "save-bookmark",
                "--url",
                "https://example.com",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(proc_human.returncode, 0, proc_human.stderr)
        self.assertIn("DRY RUN POST https://tryblume.ai/api/bookmarks", proc_human.stdout)

        proc_err = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "save-bookmark",
                "--url",
                "not-a-url",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(proc_err.returncode, 1)
        self.assertIn("Error: URL must be an absolute http(s) link.", proc_err.stderr)


if __name__ == "__main__":
    unittest.main()
