"""CLI entry point: python -m ird.cli <subcommand> [options]"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def cmd_deploy(args: argparse.Namespace) -> None:
    from .commands.deploy import deploy
    deploy(args.config, Path(args.session))


def cmd_status(args: argparse.Namespace) -> None:
    from .connection import load_or_bootstrap_session
    from .commands.status import status
    session_path = Path(args.session)
    session = load_or_bootstrap_session(session_path, args.config)
    status(session, watch=args.watch, poll_interval=args.interval,
           session_path=session_path, config_path=args.config)


def cmd_pull(args: argparse.Namespace) -> None:
    from .connection import load_or_bootstrap_session
    from .commands.pull import pull
    session_path = Path(args.session)
    session = load_or_bootstrap_session(session_path, args.config)
    pull(session, args.local_dir, session_path=session_path,
         config_path=args.config)


def cmd_release(args: argparse.Namespace) -> None:
    from .commands.release import release
    release(Path(args.session), config_path=args.config)


def cmd_repackage(args: argparse.Namespace) -> None:
    from .connection import load_or_bootstrap_session
    from .commands.repackage import repackage
    session_path = Path(args.session)
    session = load_or_bootstrap_session(session_path, args.config)
    repackage(session, session_path=session_path, config_path=args.config)


def cmd_analyze(args: argparse.Namespace) -> None:
    from .commands.analyze import analyze
    analyze(
        args.data_dir,
        args.config,
        polaris_big_dir=args.polaris_big_dir,
        stage_method=args.stage_method,
    )


def cmd_stage(args: argparse.Namespace) -> None:
    from .config import load_config
    from .local.polaris_big import ensure_polaris_big
    from .local.polaris_big_patch import patch_polaris_big_for_tag
    from .local.stage import stage_test_data
    rtl_config, model_config = load_config(args.config)
    ensure_polaris_big(
        args.polaris_big_dir, model_config.git_url, model_config.git_branch,
    )
    patch_polaris_big_for_tag(
        args.polaris_big_dir, rtl_config.rtl_tag, rtl_config.previous_rtl_tag,
    )
    stage_test_data(
        Path(args.data_dir) / rtl_config.rtl_tag,
        rtl_config.rtl_tag,
        args.polaris_big_dir,
        method=args.method,
    )


def cmd_run(args: argparse.Namespace) -> None:
    from .commands.run import run
    run(args.config, args.local_dir, Path(args.session))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="ird.cli",
        description="RTL Test Runner — Batch Job Architecture",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # deploy
    p_deploy = subparsers.add_parser("deploy", help="Reserve IRD, ship worker, launch remote job")
    p_deploy.add_argument("--config", required=True, help="Path to run_config.json")
    p_deploy.add_argument("--session", default="session.json", help="Session file path")
    p_deploy.set_defaults(func=cmd_deploy)

    # status
    p_status = subparsers.add_parser("status", help="Check remote job progress")
    p_status.add_argument("--watch", action="store_true", help="Poll until done")
    p_status.add_argument("--interval", type=int, default=30, help="Poll interval in seconds")
    p_status.add_argument("--session", default="session.json", help="Session file path")
    p_status.add_argument("--config", default=None, help="Path to run_config.json (overrides session reservation settings)")
    p_status.set_defaults(func=cmd_status)

    # pull
    p_pull = subparsers.add_parser("pull", help="Pull data_package from remote")
    p_pull.add_argument("--local-dir", default=".", help="Local directory to store data")
    p_pull.add_argument("--session", default="session.json", help="Session file path")
    p_pull.add_argument("--config", default=None, help="Path to run_config.json (overrides session reservation settings)")
    p_pull.set_defaults(func=cmd_pull)

    # release
    p_release = subparsers.add_parser("release", help="Release IRD instance")
    p_release.add_argument("--session", default="session.json", help="Session file path")
    p_release.add_argument("--config", default=None, help="Path to run_config.json (overrides session reservation settings)")
    p_release.set_defaults(func=cmd_release)

    # repackage
    p_repackage = subparsers.add_parser("repackage", help="Rebuild data_package/ on remote without re-running tests")
    p_repackage.add_argument("--session", default="session.json", help="Session file path")
    p_repackage.add_argument("--config", default=None, help="Path to run_config.json (overrides session reservation settings)")
    p_repackage.set_defaults(func=cmd_repackage)

    # analyze
    p_analyze = subparsers.add_parser(
        "analyze",
        help="Stage pulled data into polaris_big/__ext and run run_rtl_neosim_correlation.py",
    )
    p_analyze.add_argument("--data-dir", default=".",
                           help="Parent of the pulled <rtl_tag>/ directory (default: .)")
    p_analyze.add_argument("--config", required=True, help="Path to run_config.json")
    p_analyze.add_argument("--polaris-big-dir", default="polaris_big",
                           help="Path to polaris_big checkout (default: polaris_big)")
    p_analyze.add_argument("--stage-method", choices=("copy", "symlink"), default="copy",
                           help="copy (default, tar-safe) or symlink (dev-only)")
    p_analyze.set_defaults(func=cmd_analyze)

    # stage (standalone: just materialize __ext/rtl_test_data_set/<tag>/)
    p_stage = subparsers.add_parser(
        "stage",
        help="Stage pulled ws-tensix/{src,rsim} into polaris_big/__ext/rtl_test_data_set/<tag>",
    )
    p_stage.add_argument("--data-dir", default=".",
                         help="Parent of the pulled <rtl_tag>/ directory (default: .)")
    p_stage.add_argument("--config", required=True, help="Path to run_config.json")
    p_stage.add_argument("--polaris-big-dir", default="polaris_big",
                         help="Path to polaris_big checkout (default: polaris_big)")
    p_stage.add_argument("--method", choices=("copy", "symlink"), default="copy",
                         help="copy (default, tar-safe) or symlink (dev-only)")
    p_stage.set_defaults(func=cmd_stage)

    # run (convenience: deploy -> status --watch -> pull -> analyze -> release)
    p_run = subparsers.add_parser("run", help="Full pipeline: deploy → status → pull → analyze → release")
    p_run.add_argument("--config", required=True, help="Path to run_config.json")
    p_run.add_argument("--local-dir", default=".", help="Local directory to store data")
    p_run.add_argument("--session", default="session.json", help="Session file path")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    args.func(args)


if __name__ == "__main__":
    main()
