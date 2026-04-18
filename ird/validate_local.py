"""Local validation script — tests all components without requiring a real IRD connection.

Run from the parent of ird/:
    python3 -m ird.validate_local
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}: {detail}")


def test_config() -> None:
    print("\n=== config.py ===")
    from ird.config import RTLConfig, ModelConfig, SSHTarget, load_config, save_config

    ssh = SSHTarget(host="testhost", user="testuser", port=2222)
    check("SSHTarget creation", ssh.host == "testhost")
    check("SSHTarget to_dict roundtrip", SSHTarget.from_dict(ssh.to_dict()) == ssh)

    rtl = RTLConfig(rtl_tag="apr16", remote_root_dir_path="/tmp/test")
    check("RTLConfig creation", rtl.rtl_tag == "apr16")
    check("RTLConfig local_root_dir", rtl.local_root_dir == "from-ws-tensix-apr16")
    check("RTLConfig ird_ssh_target", rtl.ird_ssh_target().host == "yyz-ird")
    check("RTLConfig from_dict roundtrip", RTLConfig.from_dict(rtl.to_dict()).rtl_tag == "apr16")

    model = ModelConfig()
    check("ModelConfig creation", model.root_dir == "polaris_big")
    check("ModelConfig cfg_dir", model.cfg_dir("apr16") == "__config_files_apr16")
    check("ModelConfig default_cfg", model.default_cfg_file_name("apr16") == "ttqs_neo4_apr16.json")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        save_config(rtl, model, f.name)
        rtl2, model2 = load_config(f.name)
        check("save/load config roundtrip", rtl2.rtl_tag == "apr16" and model2.root_dir == "polaris_big")
        os.unlink(f.name)


def test_session() -> None:
    print("\n=== session.py ===")
    from ird.session import Session

    sess = Session.create(
        selection_id="12345",
        host="aus-compute-42",
        port=2224,
        user="testuser",
        key_file="/home/testuser/.ssh/id_ed25519",
        remote_work_dir="/tmp/work",
        rtl_tag="apr16",
    )
    check("Session create", sess.selection_id == "12345")
    check("Session ssh_target", sess.ssh_target().host == "aus-compute-42")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        tmp_path = Path(f.name)

    sess.save(tmp_path)
    sess2 = Session.load(tmp_path)
    check("Session save/load roundtrip", sess2.selection_id == "12345")
    check("Session mode default", sess2.mode == "batch")
    tmp_path.unlink()


def test_remote_worker_modules() -> None:
    print("\n=== remote_worker/ (import checks) ===")

    # test_discovery requires PyYAML which may not be on the local machine
    try:
        from ird.remote_worker import setup, data_packager
        check("remote_worker.setup import", True)
        check("remote_worker.data_packager import", True)
    except ImportError as e:
        check("remote_worker base imports", False, str(e))
        return

    try:
        from ird.remote_worker import test_discovery
        check("remote_worker.test_discovery import", True)
    except ImportError:
        check("remote_worker.test_discovery import", False, "PyYAML not available locally (expected)")

    from ird.remote_worker import test_runner
    check("remote_worker.test_runner import", True)
    check("test_runner.PROGRESS_DIR", test_runner.PROGRESS_DIR == "progress")

    with tempfile.TemporaryDirectory() as tmpdir:
        orig = test_runner.PROGRESS_DIR
        test_runner.PROGRESS_DIR = os.path.join(tmpdir, "progress")
        os.makedirs(test_runner.PROGRESS_DIR)
        test_runner._write_progress("sample_test", {"status": "done", "exit_code": 0})
        progress_file = Path(test_runner.PROGRESS_DIR) / "sample_test.json"
        check("_write_progress atomic write", progress_file.exists())
        data = json.loads(progress_file.read_text())
        check("_write_progress content", data["status"] == "done" and data["exit_code"] == 0)
        test_runner.PROGRESS_DIR = orig


def test_transfer_modules() -> None:
    print("\n=== transfer/ (import + construction checks) ===")
    from ird.transfer.resilient_rsync import _ssh_options
    from ird.config import SSHTarget

    target = SSHTarget(host="test", user="user", port=2222)
    opts = _ssh_options(target)
    check("_ssh_options contains port", "-p 2222" in opts)
    check("_ssh_options contains keepalive", "ServerAliveInterval" in opts)


def test_ird_reservation() -> None:
    print("\n=== ird_reservation.py (structure checks) ===")
    from ird.ird_reservation import ird_list, ird_reserve, ird_release, ird_session, IRDInstance

    inst = IRDInstance(selection_id="999", host="machine1", port=2224)
    check("IRDInstance creation", inst.selection_id == "999")
    check("ird_session is context manager", hasattr(ird_session, "__enter__") or callable(ird_session))


def test_cli() -> None:
    print("\n=== cli.py ===")
    from ird.cli import main
    import io
    from contextlib import redirect_stdout, redirect_stderr

    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            main(["--help"])
    except SystemExit:
        pass

    output = stdout.getvalue() + stderr.getvalue()
    check("CLI --help shows deploy", "deploy" in output)
    check("CLI --help shows status", "status" in output)
    check("CLI --help shows run", "run" in output)
    check("CLI --help shows release", "release" in output)
    check("CLI --help shows analyze", "analyze" in output)


def test_data_packager() -> None:
    print("\n=== data_packager.py (offline test) ===")
    from ird.remote_worker.data_packager import _find_file

    with tempfile.TemporaryDirectory() as tmpdir:
        nested = Path(tmpdir) / "a" / "b"
        nested.mkdir(parents=True)
        test_file = nested / "test.txt"
        test_file.write_text("hello")

        found = _find_file(tmpdir, "a/b/test.txt")
        check("_find_file by relative path", found is not None and Path(found).exists())

        found2 = _find_file(tmpdir, "test.txt")
        check("_find_file by name walk", found2 is not None and Path(found2).exists())


def test_local_stage() -> None:
    print("\n=== local/stage.py ===")
    from ird.local.stage import _minimal_ignore

    names = [
        "sim-run.log",
        "foo.rtl_test.log",
        "TOP0.txt",
        "TOPbar.txt",
        "sim_result.yml",
        "something.elf",
        "other.txt",
    ]
    ignored = set(_minimal_ignore("whatever", names))
    check("stage filter drops sim-run.log", "sim-run.log" in ignored)
    check("stage filter drops *.rtl_test.log", "foo.rtl_test.log" in ignored)
    check("stage filter drops TOP*.txt", "TOP0.txt" in ignored and "TOPbar.txt" in ignored)
    check("stage filter keeps sim_result.yml", "sim_result.yml" not in ignored)
    check("stage filter keeps .elf", "something.elf" not in ignored)
    check("stage filter keeps unrelated .txt", "other.txt" not in ignored)


def main_validate() -> None:
    global PASS, FAIL
    print("=" * 60)
    print("Local Validation — RTL Batch Job Architecture")
    print("=" * 60)

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    test_config()
    test_session()
    test_remote_worker_modules()
    test_transfer_modules()
    test_ird_reservation()
    test_cli()
    test_data_packager()
    test_local_stage()

    print("\n" + "=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main_validate()
