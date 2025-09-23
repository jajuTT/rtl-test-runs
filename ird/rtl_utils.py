#!/usr/bin/env python

import collections
import contextlib
import datetime
import fabric
import functools
import getpass
import itertools
import json
import multiprocessing
import os
import paramiko
import paramiko.ssh_exception
import pathlib
import shlex
import shutil
import subprocess
import sys
import yaml

class yaml_files:
    @staticmethod
    def get_value_at_key_from_stream(key, stream):
        data = yaml.safe_load(stream)

        if data is None or not isinstance(data, dict):
            raise Exception("Error: YAML content is empty or not a dictionary")

        if not key in data.keys():
            raise Exception(f"- error: could not find key {key} in given stream. available keys: {data.keys()}")

        return data[key]

    @staticmethod
    def get_value_at_key_from_file(key, file_name):
        if not os.path.isfile(file_name):
            raise Exception("- error: given file {file_name} does not exist")

        with open(file_name) as stream:
            return yaml_files.get_value_at_key_from_stream(key, stream)

class copy:
    @staticmethod
    def update_known_hosts(host: str, new_key: paramiko.PKey):
        # Replace any stored host-key for *host* with *new_key* in ~/.ssh/known_hosts.
        known_hosts = os.path.expanduser("~/.ssh/known_hosts")
        host_keys = paramiko.HostKeys()
        if os.path.exists(known_hosts):
            host_keys.load(known_hosts)

        host_keys.pop(host, None)# delete old line(s)
        host_keys.add(host, new_key.get_name(), new_key)
        host_keys.save(known_hosts)
        print(f"- updated host key for {host}")

    @staticmethod
    def safe_connection(**conn_kwargs) -> fabric.Connection:
        # Fabric connection that fixes a changed host key after *you* have decided the new key is legitimate.
        while True:
            try:
                return fabric.Connection(**conn_kwargs)
            except paramiko.BadHostKeyException as exc:
                print(f"- Host key for {exc.hostname} changed!")
                print("   - Old fingerprint:", exc.expected_key.get_fingerprint().hex())
                print("   - New fingerprint:", exc.key.get_fingerprint().hex())

                # TODO:  VERIFY new fingerprint out-of-band before trusting it!
                user_ok = input("Trust the new key? [y/N] ").lower() == "y"
                if not user_ok:
                    raise

                copy.update_known_hosts(exc.hostname, exc.key)
                # loop again and reconnect with fresh file


    @staticmethod
    def copy_dir_from_remote_to_local(hostname, username, port, remote_dir, local_dir, mode = ""):
        if ("force" == mode) and pathlib.Path(local_dir).exists():
            shutil.rmtree(local_dir)

        parent_dir_path = pathlib.Path(local_dir).parent
        parent_dir_path.mkdir(parents = True, exist_ok = True) # create the directory if it doesn't exist.

        # print(f"+ Copying {remote_dir} directory locally at {parent_dir_path}")
        with fabric.Connection(hostname, user = username) as conn:
            cmd = f"rsync -az -e 'ssh -p {port}' {username}@{hostname}:{remote_dir} {parent_dir_path}"
            print(f"- executing command: {cmd}")
            conn.local(cmd, hide = True)

class test_names:
    @staticmethod
    def get_file_names_incl_path(root_dir, file_name):
        file_names = []
        for pwd, _, files in os.walk(root_dir):
            if file_name in files:
                file_names.append(os.path.join(pwd,file_name))

        return file_names

    @staticmethod
    def get_file_name_incl_path(root_dir, file_name):
        if file_name.startswith(root_dir) and os.path.isfile(file_name):
            return file_name

        file_names = test_names.get_file_names_incl_path(root_dir, file_name)

        if 0 == len(file_names):
            raise Exception(f"- error: could not find {file_name} in directory {root_dir}")
        elif 1 == len(file_names):
            return file_names[0]
        else:
            msg = f"- error: multiple files with name {file_name} found:\n"
            for ele in file_names:
                msg += f"  - {ele}\n"

                msg.rstrip()

            raise Exception(msg)

    @staticmethod
    def get_dirs_incl_path(root_dir, dir_name):
        dir_names = []
        for pwd, _, _ in os.walk(root_dir):
            if pwd.endswith(dir_name):
                dir_names.append(pwd)

        return dir_names

    @staticmethod
    def get_dir_incl_path(root_dir, dir_name):
        if dir_name.startswith(root_dir) and os.path.isfile(dir_name):
            return dir_name

        dir_names = test_names.get_dirs_incl_path(root_dir, dir_name)

        if 0 == len(dir_names):
            raise Exception(f"- error: could not find {dir_name} in directory {root_dir}")
        elif 1 == len(dir_names):
            return dir_names[0]
        else:
            msg = f"- error: multiple directories with name {dir_name} found:\n"
            for ele in dir_names:
                msg += f"  - {ele}\n"

                msg.rstrip()

            raise Exception(msg)

    @staticmethod
    def get_all_tests(yaml_file_name):
        with open(yaml_file_name) as stream:
            data = yaml.safe_load(stream)
            if not "tests" in data.keys():
                print(f"- WARNING: could not find tests section in file {yaml_file_name}, returning")
                return
            return set([test["test-name"] for test in data["tests"]])

    @staticmethod
    def get_tags(project_yaml_incl_path: str,
        suites = None,
        tags = None):
        def get_tags_from_suites(project_yaml_incl_path, suites):
            with open(project_yaml_incl_path) as stream:
                proj = yaml.safe_load(stream)
                key_suites = "suites"
                if not key_suites in proj.keys():
                    raise Exception(f"- error: no {key_suites} found in file {project_yaml_incl_path}")

                suites_names_from_proj = dict([(suite["suite-name"], idx) for idx, suite in enumerate(proj["suites"])])

                # suites_names_from_proj = [(suite["suite-name"], idx) for idx, suite in enumerate(proj[key_suites])]
                # suites_as_list_len = len(suites_names_from_proj)
                # suites_names_from_proj = dict([(suite["suite-name"], idx) for idx, suite in enumerate(proj["suites"])])
                # suites_as_dict_len = len(suites_names_from_proj)
                # if suites_as_list_len != suites_as_dict_len:
                #     msg = f"- error: duplicate suite names found. List of suite names when converted to dict, has different length. Suites length as list: {suites_as_list_len}, suites length as dict: {suites_as_dict_len}"
                #     slist = [suite["suite-name"] for idx, suite in enumerate(proj["suites"])]
                #     slistc = collections.Counter(slist)
                #     print(slistc.most_common())
                #     raise Exception(msg)

                if isinstance(suites, str):
                    suites = [suites]

                if not isinstance(suites, (list, tuple, set)):
                    raise Exception(f"- error: expect suites type to be list/tuple/set. Type of given suites is {type(suites)}")

                tags = set()
                for suite in suites:
                    if suite in suites_names_from_proj.keys():
                        tags.update(proj[key_suites][suites_names_from_proj[suite]]['tags'])
                    else:
                        print(f"- WARNING: suite {suite} is not present in list of suite names obtained from project.yaml")

                return tags

        m_tags = set()
        if suites:
            m_tags.update(get_tags_from_suites(project_yaml_incl_path, suites))

        if tags:
            if isinstance(tags, str):
                m_tags.add(tags)
            elif isinstance(tags, (list, set, tuple)):
                assert all(isinstance(ele, str) for ele in tags), "- error: expected all elements of tags to be of type str"
                m_tags.update(tags)

        return m_tags

    @staticmethod
    def get_tests_from_file(project_yaml_incl_path, yaml_file_incl_path, suites, tags, tests):
        def get_tests_with_tags_from_file(yaml_file_incl_path, tags):
            import re

            key_tests = "tests"
            tests = set()

            with open(yaml_file_incl_path) as stream:
                data = yaml.safe_load(stream)
                if key_tests in data.keys():
                    for test in data[key_tests]:
                        if any(re.match(test_tag, tag) for test_tag in test["tags"] for tag in tags):
                            tests.add(test["test-name"])

            return tests

        assert isinstance(yaml_file_incl_path, str), f"- error: expected file_name to be a str, received type: {type(yaml_file_incl_path)}"
        assert isinstance(project_yaml_incl_path, str), f"- error: expected project_yaml to be a str, received type: {type(project_yaml_incl_path)}"

        m_tests = set()
        m_tests.update(get_tests_with_tags_from_file(yaml_file_incl_path, test_names.get_tags(project_yaml_incl_path, suites = suites, tags = tags)))

        if tests:
            all_tests = test_names.get_all_tests(yaml_file_incl_path)
            for test in tests:
                if test not in all_tests:
                    print(f"- WARNING: {test} not present in file {yaml_file_incl_path}")
                else:
                    m_tests.add(test)

        return m_tests

    @staticmethod
    def get_tests(args):
        def copy_infra_dir(args):
            assert isinstance(args, dict), "- error: expected args to be a dict"
            key_force = "force"
            key_local_root_dir = "local_root_dir"
            key_local_root_dir_path = "local_root_dir_path"
            key_project_yaml = "project.yaml"
            key_remote_root_dir = "remote_root_dir"
            key_remote_root_dir_path = "remote_root_dir_path"
            key_copy_server_hostname = "copy_server_hostname"
            key_copy_server_username = "copy_server_username"
            key_copy_server_port = "copy_server_port"

            for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
                assert key in args.keys(), f"- error: {key} not found in given args dict"

            remote_root_dir_incl_path = os.path.join(args[key_remote_root_dir_path], args[key_remote_root_dir])
            local_root_dir_incl_path = os.path.join(args[key_local_root_dir_path], args[key_local_root_dir])

            infra_str = "infra"
            local_infra_dir_incl_path = os.path.join(local_root_dir_incl_path, infra_str)
            if args[key_force] and os.path.exists(local_infra_dir_incl_path):
                shutil.rmtree(local_infra_dir_incl_path)

            if not os.path.exists(local_infra_dir_incl_path):
                remote_infra_dir_incl_path = os.path.join(remote_root_dir_incl_path, infra_str)
                copy.copy_dir_from_remote_to_local(
                    hostname = args[key_copy_server_hostname],
                    username = args[key_copy_server_username],
                    port = args[key_copy_server_port],
                    remote_dir = remote_infra_dir_incl_path,
                    local_dir = local_infra_dir_incl_path)

                project_yaml_name = args[key_project_yaml]
                project_yamls = []
                for pwd, _, files in os.walk(local_infra_dir_incl_path):
                    for file in files:
                        if file == project_yaml_name:
                            project_yamls.append(os.path.join(pwd, file))

                if 0 == len(project_yamls):
                    raise Exception(f"- {local_infra_dir_incl_path} does not contain {project_yaml_name} file")
                elif 1 == len(project_yamls):
                    pass
                else:
                    msg = f"- error: multiple files with name {project_yaml_name} found. the files are:"
                    for ele in project_yamls:
                        msg += f"  - {ele}\n"

                    raise Exception(msg.rstrip())

            return local_infra_dir_incl_path

        assert isinstance(args, dict), "- error: expected args to be a dict"
        key_project_yaml = "project.yaml"
        key_yaml_files = "yaml_files"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in args.keys(), f"- error: {key} not found in given args dict"

        local_infra_dir_incl_path = copy_infra_dir(args)
        assert os.path.isdir(local_infra_dir_incl_path), f"- error: {local_infra_dir_incl_path} either doesn't exist or is not a directory."

        key_suites = "suites"
        key_tags = "tags"
        key_tests = "tests"

        project_yaml_incl_path = test_names.get_file_name_incl_path(local_infra_dir_incl_path, args[key_project_yaml])

        m_tests = set()
        for file_name, file_args in args[key_yaml_files].items():
            file_name_incl_path = test_names.get_file_name_incl_path(local_infra_dir_incl_path, file_name)

            suites = None
            tags = None
            tests = None

            if isinstance(file_args, dict):
                if key_suites in file_args.keys() and file_args[key_suites]:
                    suites = file_args[key_suites]

                if key_tags in file_args.keys() and file_args[key_tags]:
                    tags = file_args[key_tags]

                if key_tests in file_args.keys() and file_args[key_tests]:
                    tests = file_args[key_tests]

            if (not suites) and (not tags) and (not tests):
                m_tests_per_file = test_names.get_all_tests(file_name_incl_path)
                print(f"- Number of tests from file {file_name}: {len(m_tests_per_file)} (all tests)")
            else:
                m_tests_per_file = test_names.get_tests_from_file(project_yaml_incl_path, file_name_incl_path, suites = suites, tags = tags, tests = tests)
                print(f"- Number of tests from file {file_name}: {len(m_tests_per_file)} (suites: {suites}, tags: {tags}, tests: {tests})")

            m_tests.update(m_tests_per_file)

        return m_tests

class rtl_tests:
    @staticmethod
    def execute_test(test_id, test, args):
        assert isinstance(args, dict), "- error: expected args to be a dict"
        key_debug_dir             = "debug_dir"
        key_debug_dir_path        = "debug_dir_path"
        key_force                 = "force"
        key_hostname              = "hostname"
        key_rtl_log_file_suffix   = "rtl_log_file_suffix"
        key_port                  = "port"
        key_remote_root_dir       = "remote_root_dir"
        key_remote_root_dir_path  = "remote_root_dir_path"
        key_test_dir_suffix       = "test_dir_suffix"
        key_username              = "username"
        key_sim_result_yaml       = "sim_result.yaml"
        key_sim_result_yaml_key_result = "sim_result.yaml_key_result"
        key_sim_result_yaml_key_result_val_PASS = "sim_result.yaml_key_result_val_PASS"
        key_local_root_dir       = "local_root_dir"
        key_local_root_dir_path  = "local_root_dir_path"
        key_rtl_tag              = "rtl_tag"
        key_copy_server_hostname = "copy_server_hostname"
        key_copy_server_username  = "copy_server_username"
        key_copy_server_port      = "copy_server_port"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in args.keys(), f"- error: {key} not found in given args dict"

        rel_log_file_dir = os.path.join(args[key_debug_dir_path], args[key_debug_dir], test + args[key_test_dir_suffix])
        log_file = test + args[key_rtl_log_file_suffix]

        check_local_files = True if not args[key_force] else False
        check_remote_files = not check_local_files
        if check_local_files:
            local_root_dir_incl_path  = os.path.join(args[key_local_root_dir_path], args[key_local_root_dir])
            log_file_dir              = os.path.join(local_root_dir_incl_path, rel_log_file_dir)
            sim_result_yaml_incl_path = os.path.join(log_file_dir, args[key_sim_result_yaml])
            if os.path.isfile(sim_result_yaml_incl_path):
                with open(sim_result_yaml_incl_path, "r") as sim_result_yaml_file:
                    data = yaml.safe_load(sim_result_yaml_file.read())
                    assert isinstance(data, dict), f"- error: could not obtain correct YAML mapping from file {sim_result_yaml_incl_path}"
                    assert args[key_sim_result_yaml_key_result] in data.keys(), f"- error: key {args[key_sim_result_yaml_key_result]} not found in file {sim_result_yaml_incl_path}"
                    is_test_status_pass = data[args[key_sim_result_yaml_key_result]] == args[key_sim_result_yaml_key_result_val_PASS]
                    if not is_test_status_pass:
                        check_remote_files = True
            else:
                check_remote_files = True

        if check_remote_files:
            hostname = args[key_copy_server_hostname]
            username = args[key_copy_server_username]
            port = args[key_copy_server_port]

            if not hostname or not username or not port:
                hostname = args[key_hostname]
                username = args[key_username]
                port     = args[key_port]

            if not hostname or not username or not port:
                print(f"- no hostname, username or port specified, can not check status of test {test}, returning")
                return

            remote_root_dir_incl_path        = os.path.join(args[key_remote_root_dir_path], args[key_remote_root_dir])
            local_root_dir_incl_path         = os.path.join(args[key_local_root_dir_path], args[key_local_root_dir])
            remote_log_file_dir              = os.path.join(remote_root_dir_incl_path, rel_log_file_dir)
            remote_log_file_incl_path        = os.path.join(remote_log_file_dir, log_file)
            remote_sim_result_yaml_incl_path = os.path.join(remote_log_file_dir, args[key_sim_result_yaml])

            is_test_status_pass = False
            with fabric.Connection(
                host = hostname,
                user = username,
                port = port) as conn:

                with conn.sftp() as sftp:
                    if args[key_force]:
                        with contextlib.suppress(FileNotFoundError):
                            sftp.remove(remote_sim_result_yaml_incl_path)

                    with contextlib.suppress(FileNotFoundError), sftp.open(remote_sim_result_yaml_incl_path, "r") as remote_file:
                        data = yaml.safe_load(remote_file.read().decode("utf-8"))
                        assert isinstance(data, dict), f"- error: could not obtain correct YAML mapping from file {remote_sim_result_yaml_incl_path} on {conn.host}"
                        assert args[key_sim_result_yaml_key_result] in data.keys(), f"- error: key {args[key_sim_result_yaml_key_result]} not found in file {remote_sim_result_yaml_incl_path} on {conn.host}"
                        is_test_status_pass = data[args[key_sim_result_yaml_key_result]] == args[key_sim_result_yaml_key_result_val_PASS]

            if (not is_test_status_pass):
                hostname = args[key_hostname]
                username = args[key_username]
                port     = args[key_port]

                if not hostname or not username or not port:
                    print(f"- WARNING: while test {test} status is not pass, no hostname, username or port specified to re-run the test.")
                else:
                    with fabric.Connection(
                        host = hostname,
                        user = username,
                        port = port) as conn:

                        with conn.cd(remote_root_dir_incl_path):
                            cmds = []
                            cmds.append(f"pwd")
                            if args[key_rtl_tag] in set(["feb19", "mar18"]):
                                cmds.append(f"source SETUP.cctb.sh")
                            else:
                                cmds.append(f"source SETUP.cctb.local.sh")
                            cmds.append(f"mkdir -p {remote_log_file_dir}")
                            cmds.append(f"rsim run_test --test {test} > {remote_log_file_incl_path} 2>&1")

                            cmd = ' && '.join(cmds)
                            print(f"- test ID {test_id}. executing command {cmd} on server {hostname}, port {port}")
                            result = conn.run(cmd, warn = True, pty = True, hide = True) # warn: yes, move to next

                            if result.failed:
                                print(f"- test {test!r} execuition failed")
            else:
                print(f"- test ID {test_id}. test: {test!r}. pass: {is_test_status_pass}")

            # copy data
            copy.copy_dir_from_remote_to_local(
                hostname=args[key_copy_server_hostname],
                username=args[key_copy_server_username],
                port=args[key_copy_server_port],
                remote_dir=remote_log_file_dir,
                local_dir=os.path.join(local_root_dir_incl_path, rel_log_file_dir))

    @staticmethod
    def execute_tests(tests, args):
        assert isinstance(args, dict), "- error: expected args to be a dict"
        key_num_processes = "num_processes"
        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in args.keys(), f"- error: {key} not found in given args dict"

        num_processes = min(args[key_num_processes], len(tests))
        print(f"- Number of RTL tests to execute:                    {len(tests)}")
        print(f"- Number of parallel processes to execute RTL tests: {num_processes}")

        with multiprocessing.Pool(processes = num_processes) as pool:
            test_results = pool.starmap(rtl_tests.execute_test, [(idx, test, args) for idx, test in enumerate(tests)])

    @staticmethod
    def copy_partial_src(args):
        assert isinstance(args, dict), "- error: expected args to be a dict"
        key_force = "force"
        key_local_root_dir = "local_root_dir"
        key_local_root_dir_path = "local_root_dir_path"
        key_num_processes = "num_processes"
        key_remote_root_dir = "remote_root_dir"
        key_remote_root_dir_path = "remote_root_dir_path"
        key_src_dir = "src_dir"
        key_copy_server_hostname = "copy_server_hostname"
        key_copy_server_username  = "copy_server_username"
        key_copy_server_port      = "copy_server_port"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in args.keys(), f"- error: {key} not found in given args dict"

        remote_src_dir_incl_path = os.path.join(args[key_remote_root_dir_path], args[key_remote_root_dir], args[key_src_dir])
        local_src_dir_incl_path = os.path.join(args[key_local_root_dir_path], args[key_local_root_dir], args[key_src_dir])

        dirs_to_copy = ["firmware", "hardware", "meta", "verif/tensix/tests"]
        dirs_to_copy = [dir_name for dir_name in dirs_to_copy if (not os.path.exists(os.path.join(local_src_dir_incl_path, dir_name))) or args[key_force]]
        for dir_name in dirs_to_copy:
            if not os.path.exists(os.path.join(local_src_dir_incl_path, dir_name)):
                print(f"- directory {dir_name} does not exist in {local_src_dir_incl_path}")
        num_processes = min(args[key_num_processes], len(dirs_to_copy))

        if num_processes > 0:
            with multiprocessing.Pool(processes = num_processes) as pool:
                pool.starmap(copy.copy_dir_from_remote_to_local, [(
                    args[key_copy_server_hostname],
                    args[key_copy_server_username],
                    args[key_copy_server_port],
                    os.path.join(remote_src_dir_incl_path, dir_name),
                    os.path.join(local_src_dir_incl_path, dir_name)) for dir_name in dirs_to_copy])

    @staticmethod
    def get_git_commit_id(args, file_to_read):
        key_local_root_dir = "local_root_dir"
        key_local_root_dir_path = "local_root_dir_path"
        key_remote_root_dir = "remote_root_dir"
        key_remote_root_dir_path = "remote_root_dir_path"
        key_copy_server_hostname = "copy_server_hostname"
        key_copy_server_username  = "copy_server_username"
        key_copy_server_port      = "copy_server_port"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in args.keys(), f"- error: {key} not found in given rtl args dict"

        file_to_read = os.path.join(args[key_local_root_dir_path], args[key_local_root_dir], f"{file_to_read}")

        if os.path.isfile(file_to_read):
            with open(file_to_read, "r") as f:
                commit_id = f.read().strip()
                return commit_id
        else:
            path = os.path.join(args[key_remote_root_dir_path], args[key_remote_root_dir])

            with fabric.Connection(args[key_copy_server_hostname], user = args[key_copy_server_username], port = args[key_copy_server_port]) as conn:
                cmd = f"git -C {path} rev-parse --short HEAD"
                result = conn.run(cmd, hide=True)
                if result.exited:
                    raise Exception(f"- error: could not execute {cmd} on server {args[key_copy_server_hostname]}.")

                return result.stdout.strip()

        raise Exception(f"- error: could not determine git commit ID for {path}.")

    @staticmethod
    def set_rtl_git_commit_id(rtl_args):
        key_rtl_tag = "rtl_tag"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in rtl_args.keys(), f"- error: {key} not found in given args dict"

        tags_commit_ids = {
            "feb19" : "be7027f30",
            "mar18" : "b7230836b",
            "jul1"  : "ed6b8e20c",
            "jul27" : "5740f97ed"}

        key_commit_id = "rtl_git_commit_id"
        rtl_args[key_commit_id] = None

        tag = rtl_args[key_rtl_tag]
        commit_id = rtl_tests.get_git_commit_id(rtl_args, f"{key_commit_id}.txt")
        if tag in tags_commit_ids.keys():
            assert tags_commit_ids[tag] == commit_id, f"- error: git commit ID for tag {tag} is incorrect. Expected: {tags_commit_ids[tag]}, Got: {commit_id}"

        rtl_args[key_commit_id] = commit_id

        if not rtl_args[key_commit_id]:
            raise Exception(f"- error: could not determine git commit ID for rtl tag {tag}")

    @staticmethod
    def write_rtl_git_commit_id(rtl_args):

        key_rtl_tag = "rtl_tag"
        key_local_root_dir_path = "local_root_dir_path"
        key_local_root_dir = "local_root_dir"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in rtl_args.keys(), f"- error: {key} not found in given rtl args dict"

        rtl_tests.set_rtl_git_commit_id(rtl_args)

        key_commit_id = "rtl_git_commit_id"
        assert key_commit_id in rtl_args.keys(), f"- error: {key_commit_id} not found in given rtl args dict"
        assert rtl_args[key_commit_id] is not None, f"- error: could not determine git commit ID for rtl tag {rtl_args[key_rtl_tag]}"

        file_to_write = os.path.join(rtl_args[key_local_root_dir_path], rtl_args[key_local_root_dir], f"{key_commit_id}.txt")

        if not os.path.isfile(file_to_write):
            if not os.path.dirname(file_to_write):
                os.makedirs(os.path.dirname(file_to_write), exist_ok=True)

            with open(file_to_write, "w") as f:
                f.write(rtl_args[key_commit_id])

if "__main__" == __name__:
    pass