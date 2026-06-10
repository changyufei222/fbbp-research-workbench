from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
COMMON_PS1 = str(SCRIPTS_ROOT / "common.ps1").replace("\\", "/")


def _powershell_exe() -> str:
    return "powershell"


class DeerflowRuntimeConfigTests(unittest.TestCase):
    def test_import_env_file_only_if_unset_preserves_existing_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("OPENAI_BASE_URL=https://from-file.example/v1\n", encoding="utf-8")
            probe = f"""
. '{COMMON_PS1}'
$env:OPENAI_BASE_URL = 'https://existing.example/v1'
Import-EnvFile -Path '{env_path}' -Keys @('OPENAI_BASE_URL') -OnlyIfUnset
$env:OPENAI_BASE_URL | ConvertTo-Json -Compress
"""
            proc = subprocess.run(
                [_powershell_exe(), "-NoProfile", "-Command", probe],
                capture_output=True,
                text=True,
                cwd=WORKSPACE_ROOT,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
            resolved = json.loads(proc.stdout.strip())
            self.assertEqual(resolved, "https://existing.example/v1")

    def test_runtime_env_exports_deer_flow_home_and_default_fbbp_agent(self) -> None:
        probe = """
. '%s'
$runtimeEnv = Get-DeerflowRuntimeEnv
$payload = [ordered]@{
  deer_flow_home = $runtimeEnv['DEER_FLOW_HOME']
  agent_name = Get-DefaultFbbpAgentName
}
$payload | ConvertTo-Json -Compress
""" % COMMON_PS1
        proc = subprocess.run(
            [_powershell_exe(), "-NoProfile", "-Command", probe],
            capture_output=True,
            text=True,
            cwd=WORKSPACE_ROOT,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        payload = json.loads(proc.stdout.strip())
        self.assertTrue(payload["deer_flow_home"].endswith(r"deerflow_home"))
        self.assertEqual(payload["agent_name"], "fbbp-assistant")

    def test_sync_default_fbbp_agent_materializes_runtime_agent_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            probe = f"""
. '{COMMON_PS1}'
Sync-DefaultFbbpAgent -DestinationRoot '{temp_dir}'
$payload = [ordered]@{{
  config = Test-Path (Join-Path '{temp_dir}' 'agents/fbbp-assistant/config.yaml')
  soul = Test-Path (Join-Path '{temp_dir}' 'agents/fbbp-assistant/SOUL.md')
  memory = Test-Path (Join-Path '{temp_dir}' 'agents/fbbp-assistant/memory.json')
}}
$payload | ConvertTo-Json -Compress
"""
            proc = subprocess.run(
                [_powershell_exe(), "-NoProfile", "-Command", probe],
                capture_output=True,
                text=True,
                cwd=WORKSPACE_ROOT,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
            payload = json.loads(proc.stdout.strip())
            self.assertEqual(payload, {"config": True, "soul": True, "memory": True})

    def test_prepare_deerflow_config_preserves_active_upstream_model_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "fbbp.config.yaml"
            proc = subprocess.run(
                [
                    _powershell_exe(),
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(SCRIPTS_ROOT / "prepare_deerflow_config.ps1"),
                    "-OutputPath",
                    str(output_path),
                    "-Quiet",
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
            generated = output_path.read_text(encoding="utf-8")
            self.assertIn("- name: deepseek-v3.2", generated)
            self.assertIn("model: $LLM_MODEL", generated)
            self.assertIn("api_key: $OPENAI_API_KEY", generated)
            self.assertIn("base_url: $OPENAI_BASE_URL", generated)

    def test_prepare_deerflow_config_generates_extensions_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "fbbp.config.yaml"
            extensions_path = Path(temp_dir) / "extensions_config.fbbp.json"
            proc = subprocess.run(
                [
                    _powershell_exe(),
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(SCRIPTS_ROOT / "prepare_deerflow_config.ps1"),
                    "-OutputPath",
                    str(output_path),
                    "-ExtensionsOutputPath",
                    str(extensions_path),
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
            self.assertTrue(extensions_path.exists(), msg="generated DeerFlow extensions config was not created")

            payload = json.loads(extensions_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["mcpServers"]["fbbp-rag"]["type"], "http")
        self.assertTrue(payload["mcpServers"]["fbbp-rag"]["url"].endswith(":8000/mcp"))

    def test_deerflow_runtime_env_uses_generated_paths(self) -> None:
        probe = """
. '%s'
$envMap = Get-DeerflowRuntimeEnv
$payload = [ordered]@{
  config = $envMap['DEER_FLOW_CONFIG_PATH']
  extensions = $envMap['DEER_FLOW_EXTENSIONS_CONFIG_PATH']
  openai_base_url = $envMap['OPENAI_BASE_URL']
  llm_model = $envMap['LLM_MODEL']
}
$payload | ConvertTo-Json -Compress
""" % COMMON_PS1
        proc = subprocess.run(
            [_powershell_exe(), "-NoProfile", "-Command", probe],
            capture_output=True,
            text=True,
            cwd=WORKSPACE_ROOT,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        payload = json.loads(proc.stdout.strip())
        self.assertTrue(payload["config"].endswith(r"fbbp-research-workbench\generated\fbbp.config.yaml"))
        self.assertTrue(payload["extensions"].endswith(r"fbbp-research-workbench\generated\extensions_config.fbbp.json"))
        self.assertTrue(payload["openai_base_url"])
        self.assertTrue(payload["llm_model"])

    def test_deerflow_runtime_env_prefers_ragkb_env_when_mcp_env_conflicts(self) -> None:
        probe = """
. '%s'
$env:OPENAI_API_KEY = ''
$env:OPENAI_BASE_URL = ''
$env:OPENAI_API_BASE = ''
$env:BASE_URL = ''
$env:LLM_MODEL = ''
$runtimeEnv = Get-DeerflowRuntimeEnv
$payload = [ordered]@{
  openai_base_url = $runtimeEnv['OPENAI_BASE_URL']
  base_url = $runtimeEnv['BASE_URL']
}
$payload | ConvertTo-Json -Compress
""" % COMMON_PS1
        proc = subprocess.run(
            [_powershell_exe(), "-NoProfile", "-Command", probe],
            capture_output=True,
            text=True,
            cwd=WORKSPACE_ROOT,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        payload = json.loads(proc.stdout.strip())
        self.assertEqual(payload["openai_base_url"], "https://api.vectorengine.cn/v1")
        self.assertEqual(payload["base_url"], "https://api.vectorengine.cn/v1")

    def test_new_fbbp_launcher_wrappers_exist(self) -> None:
        for name in (
            "start_fbbp_http_mcp.ps1",
            "start_fbbp_http_mcp_wsl.ps1",
            "launch_fbbp_workbench.ps1",
            "run_fbbp_formal_case.ps1",
            "run_fbbp_formal_batch.ps1",
        ):
            self.assertTrue((SCRIPTS_ROOT / name).exists(), msg=f"{name} is missing")

    def test_wsl_mcp_launcher_uses_absolute_log_paths(self) -> None:
        script = (SCRIPTS_ROOT / "start_fbbp_http_mcp_wsl.sh").read_text(encoding="utf-8")

        self.assertIn('>"$OUT_LOG"', script)
        self.assertIn('2>"$ERR_LOG"', script)
        self.assertNotIn(">http_mcp.out.log", script)
        self.assertNotIn("2>http_mcp.err.log", script)

    def test_wsl_mcp_shell_launcher_supports_base64_root_overrides(self) -> None:
        script = (SCRIPTS_ROOT / "start_fbbp_http_mcp_wsl.sh").read_text(encoding="utf-8")

        self.assertIn("FBBP_WORKSPACE_ROOT_B64", script)
        self.assertIn("FBBP_REPO_ROOT_B64", script)
        self.assertIn("base64 --decode", script)

    def test_wsl_mcp_shell_launcher_supports_ascii_runtime_override(self) -> None:
        script = (SCRIPTS_ROOT / "start_fbbp_http_mcp_wsl.sh").read_text(encoding="utf-8")

        self.assertIn("FBBP_WSL_RUNTIME_ROOT", script)
        self.assertIn("/tmp/", script)

    def test_wsl_mcp_powershell_launcher_uses_http_probe(self) -> None:
        script = (SCRIPTS_ROOT / "start_fbbp_http_mcp_wsl.ps1").read_text(encoding="utf-8")

        self.assertIn("Invoke-WebRequest", script)
        self.assertIn("Test-McpEndpoint", script)
        self.assertIn("/mcp", script)

    def test_primary_mcp_launcher_supports_windows_first_with_wsl_fallback(self) -> None:
        script_path = SCRIPTS_ROOT / "start_fbbp_http_mcp.ps1"

        self.assertTrue(script_path.exists(), msg="primary MCP launcher script is missing")
        script = script_path.read_text(encoding="utf-8")
        self.assertIn("start_http_server.ps1", script)
        self.assertIn("start_fbbp_http_mcp_wsl.ps1", script)

    def test_primary_mcp_launcher_uses_shared_ragkb_env_helper(self) -> None:
        script = (SCRIPTS_ROOT / "start_fbbp_http_mcp.ps1").read_text(encoding="utf-8")

        self.assertIn("Set-RagkbEnv", script)
        self.assertIn("Ensure-LocalFormalPostgresReady", script)

    def test_common_ragkb_env_prefers_localhost_bridge_for_windows_processes(self) -> None:
        probe = """
. '%s'
Set-RagkbEnv | Out-Null
$env:PGHOST | ConvertTo-Json -Compress
""" % COMMON_PS1
        proc = subprocess.run(
            [_powershell_exe(), "-NoProfile", "-Command", probe],
            capture_output=True,
            text=True,
            cwd=WORKSPACE_ROOT,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        resolved_host = json.loads(proc.stdout.strip())
        self.assertEqual(resolved_host, "localhost")

    def test_start_wsl_pgvector_clears_legacy_local_portproxy_before_starting_postgres(self) -> None:
        script = (SCRIPTS_ROOT / "start_wsl_pgvector.ps1").read_text(encoding="utf-8")

        self.assertIn("Remove-LocalPostgresPortProxy", script)
        self.assertIn("Ensure-LocalFormalPostgresReady", script)

    def test_repair_wsl_postgres_bridge_validates_windows_query_path(self) -> None:
        script = (SCRIPTS_ROOT / "repair_wsl_postgres_bridge.ps1").read_text(encoding="utf-8")

        self.assertIn("Remove-LocalPostgresPortProxy", script)
        self.assertIn("Ensure-LocalFormalPostgresReady", script)
        self.assertIn("Test-NetConnection", script)
        self.assertIn("tcp_probe_host", script)
        self.assertIn("Test-PostgresQueryReady", script)
        self.assertIn("wsl_reachable", script)
        self.assertIn("portproxy_empty", script)

    def test_common_postgres_probe_avoids_reserved_host_parameter_name(self) -> None:
        script = (SCRIPTS_ROOT / "common.ps1").read_text(encoding="utf-8")

        self.assertNotIn("[string]$Host =", script)
        self.assertIn("[string]$ProbeHost =", script)

    def test_start_stack_core_uses_primary_mcp_launcher(self) -> None:
        script = (SCRIPTS_ROOT / "start_stack_core.ps1").read_text(encoding="utf-8")

        self.assertIn("start_fbbp_http_mcp.ps1", script)
        self.assertNotIn("start_fbtp_http_mcp_wsl.ps1", script)

    def test_common_exposes_ascii_wsl_proxy_root(self) -> None:
        probe = """
. '%s'
$path = Get-WslAsciiProxyRoot
$path | ConvertTo-Json -Compress
""" % COMMON_PS1
        proc = subprocess.run(
            [_powershell_exe(), "-NoProfile", "-Command", probe],
            capture_output=True,
            text=True,
            cwd=WORKSPACE_ROOT,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        proxy_root = json.loads(proc.stdout.strip())
        self.assertRegex(proxy_root, r"^[A-Z]:\\$")
        self.assertNotRegex(proxy_root, r"[^\x00-\x7F]")

    def test_frontend_local_root_uses_non_exfat_runtime_drive(self) -> None:
        probe = """
. '%s'
$path = Get-FrontendLocalRoot
$drive = [System.IO.Path]::GetPathRoot($path).Substring(0, 1)
$payload = [ordered]@{
  path = $path
  file_system = (Get-Volume -DriveLetter $drive).FileSystem
}
$payload | ConvertTo-Json -Compress
""" % COMMON_PS1
        proc = subprocess.run(
            [_powershell_exe(), "-NoProfile", "-Command", probe],
            capture_output=True,
            text=True,
            cwd=WORKSPACE_ROOT,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        payload = json.loads(proc.stdout.strip())
        self.assertTrue(payload["path"].endswith(r"frontend_local"))
        self.assertNotEqual(payload["file_system"], "exFAT")

    def test_frontend_next_script_prefers_js_entrypoint(self) -> None:
        probe = """
. '%s'
$path = Get-FrontendNextScript
$path | ConvertTo-Json -Compress
""" % COMMON_PS1
        proc = subprocess.run(
            [_powershell_exe(), "-NoProfile", "-Command", probe],
            capture_output=True,
            text=True,
            cwd=WORKSPACE_ROOT,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        next_script = json.loads(proc.stdout.strip())
        self.assertTrue(next_script.endswith(r"node_modules\next\dist\bin\next"), msg=next_script)
        self.assertNotIn(r"node_modules\.bin\next", next_script)

    def test_install_frontend_local_uses_default_pnpm_layout(self) -> None:
        script = (SCRIPTS_ROOT / "install_frontend_local.ps1").read_text(encoding="utf-8")

        self.assertIn("pnpm install --reporter append-only", script)
        self.assertNotIn("--node-linker=hoisted", script)

    def test_start_frontend_local_uses_webpack_mode(self) -> None:
        script = (SCRIPTS_ROOT / "start_frontend_local.ps1").read_text(encoding="utf-8")

        self.assertIn("'--webpack'", script)

    def test_start_frontend_local_exports_llm_runtime_env(self) -> None:
        script = (SCRIPTS_ROOT / "start_frontend_local.ps1").read_text(encoding="utf-8")

        self.assertIn("sync_frontend_local.ps1", script)
        self.assertIn("Get-DeerflowRuntimeEnv", script)
        self.assertIn("OPENAI_API_KEY", script)
        self.assertIn("OPENAI_BASE_URL", script)
        self.assertIn("LLM_MODEL", script)

    def test_start_frontend_local_stops_existing_frontend_before_sync_and_writes_env_local(self) -> None:
        script = (SCRIPTS_ROOT / "start_frontend_local.ps1").read_text(encoding="utf-8")

        self.assertIn("Stop-FrontendLocalProcess", script)
        self.assertLess(script.index("Stop-FrontendLocalProcess"), script.index("sync_frontend_local.ps1"))
        self.assertIn(".env.local", script)
        self.assertIn("Remove-Item $envFile", script)
        self.assertIn("NEXT_PUBLIC_BACKEND_BASE_URL", script)
        self.assertIn("NEXT_PUBLIC_LANGGRAPH_BASE_URL", script)

    def test_sync_frontend_local_preserves_runtime_env_files(self) -> None:
        script = (SCRIPTS_ROOT / "sync_frontend_local.ps1").read_text(encoding="utf-8")

        self.assertIn(".env", script)
        self.assertIn(".env.local", script)

    def test_start_frontend_local_hides_spawned_node_window(self) -> None:
        script = (SCRIPTS_ROOT / "start_frontend_local.ps1").read_text(encoding="utf-8")

        self.assertIn("-WindowStyle 'Hidden'", script)

    def test_start_deerflow_backend_hides_spawned_windows(self) -> None:
        script = (SCRIPTS_ROOT / "start_deerflow_backend.ps1").read_text(encoding="utf-8")

        self.assertGreaterEqual(script.count("-WindowStyle 'Hidden'"), 2)

    def test_primary_mcp_launcher_hides_spawned_powershell_window(self) -> None:
        script = (SCRIPTS_ROOT / "start_fbbp_http_mcp.ps1").read_text(encoding="utf-8")

        self.assertIn("-WindowStyle 'Hidden'", script)

    def test_silent_ui_launcher_exists_and_targets_workspace_page(self) -> None:
        script_path = SCRIPTS_ROOT / "start_deerflow_ui_silent.ps1"

        self.assertTrue(script_path.exists(), msg="silent DeerFlow UI launcher is missing")
        script = script_path.read_text(encoding="utf-8")
        self.assertIn("start_fullstack_local_frontend.ps1", script)
        self.assertIn("http://127.0.0.1:3000/workspace", script)
        self.assertIn("Formal results page: http://127.0.0.1:3000/fbbp", script)
        self.assertIn("Start-Process $url", script)

    def test_silent_ui_stopper_exists_and_uses_stop_stack(self) -> None:
        script_path = SCRIPTS_ROOT / "stop_deerflow_ui_silent.ps1"

        self.assertTrue(script_path.exists(), msg="silent DeerFlow UI stopper is missing")
        script = script_path.read_text(encoding="utf-8")
        self.assertIn("stop_stack.ps1", script)

    def test_ui_status_script_exists_and_checks_expected_ports(self) -> None:
        script_path = SCRIPTS_ROOT / "status_deerflow_ui.ps1"

        self.assertTrue(script_path.exists(), msg="DeerFlow UI status script is missing")
        script = script_path.read_text(encoding="utf-8")
        self.assertIn("3000", script)
        self.assertIn("8001", script)
        self.assertIn("2024", script)
        self.assertIn("8000", script)

    def test_vbs_wrappers_launch_powershell_hidden(self) -> None:
        launcher = REPO_ROOT / "Open_DeerFlow_UI.vbs"
        stopper = REPO_ROOT / "Stop_DeerFlow_UI.vbs"

        self.assertTrue(launcher.exists(), msg="Open_DeerFlow_UI.vbs is missing")
        self.assertTrue(stopper.exists(), msg="Stop_DeerFlow_UI.vbs is missing")
        self.assertIn(", 0, False", launcher.read_text(encoding="utf-8"))
        self.assertIn(", 0, False", stopper.read_text(encoding="utf-8"))

    def test_open_vbs_delegates_ui_open_to_powershell_launcher(self) -> None:
        launcher = (REPO_ROOT / "Open_DeerFlow_UI.vbs").read_text(encoding="utf-8")

        self.assertNotIn("-NoOpen", launcher)
        self.assertNotIn("WinHttp.WinHttpRequest.5.1", launcher)
        self.assertIn("start_deerflow_ui_silent.ps1", launcher)


if __name__ == "__main__":
    unittest.main()
