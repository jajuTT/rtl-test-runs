"""Discover RTL test names from infra YAML files. Uses PyYAML (available on remote)."""

from __future__ import annotations

import logging
import os
import re

import yaml

logger = logging.getLogger(__name__)


def get_tests(config: dict) -> list[str]:
    """Get the list of tests to run. Uses explicit list if provided, otherwise discovers from YAML."""
    if config.get("tests"):
        logger.info("Using explicit test list (%d tests)", len(config["tests"]))
        return sorted(config["tests"])

    ws_path = config.get("ws_tensix_path") or os.path.join(
        config["remote_root_dir_path"], config.get("remote_root_dir", "ws-tensix")
    )
    tests_dir = config.get("tests_dir", "infra/tensix/rsim/tests")
    infra_path = os.path.join(ws_path, tests_dir)

    if not os.path.isdir(infra_path):
        raise FileNotFoundError(f"Tests directory not found: {infra_path}")

    yaml_files = config.get("yaml_files", {})
    suites = config.get("suites", "postcommit")
    project_yaml_name = config.get("project_yaml", "project.yml")

    project_yaml_path = _find_file(os.path.join(ws_path, "infra"), project_yaml_name)

    all_tests: set[str] = set()
    for yaml_file, file_args in yaml_files.items():
        yaml_path = _find_file(infra_path, yaml_file)
        file_suites = file_args.get("suites", suites) if isinstance(file_args, dict) else suites
        tags = _get_tags_from_project(project_yaml_path, file_suites)
        tests = _get_tests_with_tags(yaml_path, tags)
        logger.info("Found %d tests in %s", len(tests), yaml_file)
        all_tests.update(tests)

    return sorted(all_tests)


def _find_file(root_dir: str, file_name: str) -> str:
    """Walk the directory tree to locate a file by name."""
    if os.path.isfile(file_name):
        return file_name
    if file_name.startswith(root_dir) and os.path.isfile(file_name):
        return file_name

    for dirpath, _, filenames in os.walk(root_dir):
        if file_name in filenames:
            return os.path.join(dirpath, file_name)

    raise FileNotFoundError(f"Could not find {file_name} under {root_dir}")


def _get_tags_from_project(project_yaml_path: str, suites: str | list[str]) -> set[str]:
    """Extract tag patterns from project.yml for the given suite(s)."""
    with open(project_yaml_path) as f:
        proj = yaml.safe_load(f)

    if "suites" not in proj:
        raise ValueError(f"No 'suites' key in {project_yaml_path}")

    suites_map = {s["suite-name"]: s for s in proj["suites"]}

    if isinstance(suites, str):
        suites = [suites]

    tags: set[str] = set()
    for suite_name in suites:
        if suite_name in suites_map:
            tags.update(suites_map[suite_name].get("tags", []))
        else:
            logger.warning("Suite '%s' not found in project.yml", suite_name)

    return tags


def _get_tests_with_tags(yaml_path: str, tags: set[str]) -> set[str]:
    """Extract test names from a YAML file that match any of the given tag patterns."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    if "tests" not in data:
        logger.warning("No 'tests' section in %s", yaml_path)
        return set()

    tests: set[str] = set()
    for test_entry in data["tests"]:
        test_tags = test_entry.get("tags", [])
        if any(re.match(tag_pattern, test_tag) for tag_pattern in tags for test_tag in test_tags):
            tests.add(test_entry["test-name"])

    return tests
