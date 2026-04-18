"""Remote worker entry point. Run via: python -m remote_worker job_config.json"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from . import setup, test_discovery, test_runner, data_packager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("remote_worker.log"),
    ],
)
logger = logging.getLogger("remote_worker")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m remote_worker <job_config.json>", file=sys.stderr)
        sys.exit(1)

    config_path = Path(sys.argv[1])
    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    logger.info("Remote worker started with config: %s", config_path)

    # Phase 1: Clone and build ws-tensix if needed
    logger.info("Phase 1: Setup (clone/build)")
    setup.clone_and_build_if_needed(config)

    # Phase 2: Discover tests from infra YAML
    logger.info("Phase 2: Test discovery")
    tests = test_discovery.get_tests(config)
    logger.info("Discovered %d tests", len(tests))

    # Phase 3: Run rsim tests
    logger.info("Phase 3: Running tests (mode=%s)", config.get("mode", "batch"))
    test_runner.run_all(tests, config)

    # Phase 4: Package results for local pull
    logger.info("Phase 4: Packaging data")
    data_packager.package(config)

    # Phase 5: Write DONE marker
    done_info = {
        "completed": time.time(),
        "num_tests": len(tests),
    }
    Path("DONE").write_text(json.dumps(done_info, indent=2))
    logger.info("Remote worker finished. DONE marker written.")


if __name__ == "__main__":
    main()
