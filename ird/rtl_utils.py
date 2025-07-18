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
            key_hostname = "hostname"
            key_local_root_dir = "local_root_dir"
            key_local_root_dir_path = "local_root_dir_path"
            key_port = "port"
            key_project_yaml = "project.yaml"
            key_remote_root_dir = "remote_root_dir"
            key_remote_root_dir_path = "remote_root_dir_path"
            key_username = "username"

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
                    hostname = args[key_hostname],
                    username = args[key_username],
                    port = args[key_port],
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

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in args.keys(), f"- error: {key} not found in given args dict"

        hostname = args[key_hostname]
        username = args[key_username]
        port     = args[key_port]
        with fabric.Connection(
            host = hostname,
            user = username,
            port = port) as conn:
            remote_root_dir_incl_path        = os.path.join(args[key_remote_root_dir_path], args[key_remote_root_dir])
            local_root_dir_incl_path         = os.path.join(args[key_local_root_dir_path], args[key_local_root_dir])
            log_file                         = test + args[key_rtl_log_file_suffix]
            rel_log_file_dir                 = os.path.join(args[key_debug_dir_path], args[key_debug_dir], test + args[key_test_dir_suffix])
            remote_log_file_dir              = os.path.join(remote_root_dir_incl_path, rel_log_file_dir)
            remote_log_file_incl_path        = os.path.join(remote_log_file_dir, log_file)
            remote_sim_result_yaml_incl_path = os.path.join(remote_log_file_dir, args[key_sim_result_yaml])

            is_test_status_pass = False
            with conn.sftp() as sftp:
                if args[key_force]:
                    with contextlib.suppress(FileNotFoundError):
                        sftp.remove(remote_sim_result_yaml_incl_path)

                with contextlib.suppress(FileNotFoundError), sftp.open(remote_sim_result_yaml_incl_path, "r") as remote_file:
                    data = yaml.safe_load(remote_file.read().decode("utf-8"))
                    assert isinstance(data, dict), f"- error: could not obtain correct YAML mapping from file {remote_sim_result_yaml_incl_path} on {conn.host}"
                    assert args[key_sim_result_yaml_key_result] in data.keys(), f"- error: key {args[key_sim_result_yaml_key_result]} not found in file {remote_sim_result_yaml_incl_path} on {conn.host}"
                    is_test_status_pass = data[args[key_sim_result_yaml_key_result]] == args[key_sim_result_yaml_key_result_val_PASS]

            if not is_test_status_pass:
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
            copy.copy_dir_from_remote_to_local(hostname, username, port, remote_log_file_dir, os.path.join(local_root_dir_incl_path, rel_log_file_dir))

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
        key_hostname = "hostname"
        key_local_root_dir = "local_root_dir"
        key_local_root_dir_path = "local_root_dir_path"
        key_num_processes = "num_processes"
        key_port = "port"
        key_remote_root_dir = "remote_root_dir"
        key_remote_root_dir_path = "remote_root_dir_path"
        key_src_dir = "src_dir"
        key_username = "username"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in args.keys(), f"- error: {key} not found in given args dict"

        remote_src_dir_incl_path = os.path.join(args[key_remote_root_dir_path], args[key_remote_root_dir], args[key_src_dir])
        local_src_dir_incl_path = os.path.join(args[key_local_root_dir_path], args[key_local_root_dir], args[key_src_dir])

        dirs_to_copy = ["firmware", "hardware", "meta"]
        num_processes = min(args[key_num_processes], len(dirs_to_copy))

        with multiprocessing.Pool(processes = num_processes) as pool:
            pool.starmap(copy.copy_dir_from_remote_to_local, [(
                args[key_hostname],
                args[key_username],
                args[key_port],
                os.path.join(remote_src_dir_incl_path, dir_name),
                os.path.join(local_src_dir_incl_path, dir_name)) for dir_name in dirs_to_copy])

# def get_test_names_from_given_file(file_name, args):
#     assert isinstance(args, dict), "- error: expected args to be a dict"
#     assert isinstance(file_name, str), "- error: expected file_name to be a str"
#     req_keys = ["local_root_dir", "yaml_files", "project.yaml"]
#     for key in req_keys:
#         assert key in args.keys(), f"- error: {key} not found in given args dict"

#     key_root_dir = req_keys[0]
#     key_yaml_files = req_keys[1]
#     key_project_yaml = req_keys[2]

#     yaml_files = args[key_yaml_files]
#     assert file_name in yaml_files.keys(), f"- error: could not find file {file_name} in value associated with key {key_yaml_files} in args dict"
#     file_args = yaml_files[file_name]
#     root_dir = args[key_root_dir]
#     file_name_incl_path = test_names.get_yml_file_name_incl_path(root_dir, file_name)
#     suites = None
#     tags = None
#     tests = None
#     key_suites = "suites"
#     key_tags = "tags"
#     key_tests = "tests"
#     if isinstance(file_args, dict):
#         if key_suites in file_args.keys() and file_args[key_suites]:
#             suites = file_args[key_suites]

#         if key_tags in file_args.keys() and file_args[key_tags]:
#             tags = file_args[key_tags]

#         if key_tests in file_args.keys() and file_args[key_tests]:
#             tests = file_args[key_tests]

#     if (not suites) and (not tags) and (not tests):
#         return test_names.get_all_tests_from_file(file_name_incl_path)

#     proj_yaml_incl_path = test_names.get_file_name_incl_path(root_dir, args[key_project_yaml])

# def get_test_names_from_rtl_test_bench(args):
#     """
#     1. copy tests directory locally.
#     2. run get test and return list of tests to be run.
#     3. The dest are decided as follows:
#        1. Get the tags from suites mentioned.
#        2. Add tags from arguments to tags obtained from step 1.
#           tags = tags(1) + tags_from_arguments
#        3. Identify tests associated with tags from the yml files specified in arguments.
#        4. Add test specified in arguments to the list of tests.
#           tests = tests from step 4 + tests from argument.
#     """

#     def get_test_names(suites, yml_files, tags, tests, local_infra_dir, project_yml):
#         import os
#         def get_yml_file_name_incl_path(local_infra_dir, yml_file):

#             yml_files = []
#             for pwd, _, files in os.walk(local_infra_dir):
#                 if yml_file in files:
#                     yml_files.append(os.path.join(pwd,yml_file))

#             if 0 == len(yml_files):
#                 raise Exception(f"- error: could not find {yml_file} in directory {local_infra_dir}")
#             elif 1 == len(yml_files):
#                 return yml_files[0]
#             else:
#                 msg = f"- error: multiple project yml files found:\n"
#                 for ele in yml_files:
#                     msg += f"  - {ele}\n"

#                     msg.rstrip()

#                 raise Exception(msg)

#         def get_tags_from_suites(proj_yml, suites):
#             if None == suites:
#                 return None

#             import yaml

#             with open(proj_yml) as stream:
#                 proj = yaml.safe_load(stream)
#                 suites_key_str = "suites"
#                 if not suites_key_str in proj.keys():
#                     raise Exception(f"- error: no {suites_key_str} found in file {proj_yml}")

#                 suites_names_from_proj = [(suite["suite-name"], idx) for idx, suite in enumerate(proj["suites"])]
#                 suites_as_list_len = len(suites_names_from_proj)

#                 suites_names_from_proj = dict([(suite["suite-name"], idx) for idx, suite in enumerate(proj["suites"])])
#                 suites_as_dict_len = len(suites_names_from_proj)

#                 # if suites_as_list_len != suites_as_dict_len:
#                 #     msg = f"- error: duplicate suite names found. List of suite names when converted to dict, has different length. Suites length as list: {suites_as_list_len}, suites length as dict: {suites_as_dict_len}"
#                 #     slist = [suite["suite-name"] for idx, suite in enumerate(proj["suites"])]
#                 #     slistc = collections.Counter(slist)
#                 #     print(slistc.most_common())
#                 #     raise Exception(msg)

#                 if isinstance(suites, str):
#                     suites = [suites]

#                 if not isinstance(suites, (list, tuple, set)):
#                     raise Exception(f"- error: expect suites type to be list/tuple/set. Type of given suites is {type(suites)}")

#                 tags = set()
#                 for suite in suites:
#                     if suite in suites_names_from_proj.keys():
#                         tags.update(proj[suites_key_str][suites_names_from_proj[suite]]['tags'])

#                 return tags

#             return None

#         def get_tags(proj_yml, suites, tags):
#             tags_from_suites = get_tags_from_suites(proj_yml, suites)
#             if None == tags:
#                 return tags_from_suites
#             elif isinstance(tags, str):
#                 tags_from_suites.add(tags)
#                 return tags_from_suites
#             elif isinstance(tags, (list, tuple, set)):
#                 tags_from_suites.update(tags)
#                 return tags_from_suites
#             else:
#                 raise Exception(f"- error: no method defined to add tags of type {type(tags)}")

#             return None

#         def get_tests_with_tags_from_files(yml_files, tags, local_infra_dir):
#             import re
#             import yaml

#             tests_str = "tests"
#             tests = set()

#             for yml_file in yml_files:
#                 yml_file_incl_path = get_yml_file_name_incl_path(local_infra_dir, yml_file)

#                 with open(yml_file_incl_path) as stream:
#                     yml = yaml.safe_load(stream)

#                     if tests_str in yml.keys():
#                         for test in yml[tests_str]:
#                             if any(re.match(test_tag, tag) for test_tag in test["tags"] for tag in tags):
#                                 tests.add(test["test-name"])

#             return tests

#         def get_tests(yml_files, tags, tests_dir, tests):
#             tagged_tests = get_tests_with_tags_from_files(yml_files, tags, tests_dir)
#             if None == tagged_tests:
#                 return tests

#             if None == tests:
#                 return tagged_tests

#             elif isinstance(tests, str):
#                 tagged_tests.add(tests)
#                 return tagged_tests

#             elif isinstance(tests, (list, tuple, set)):
#                 tagged_tests.update(tags)
#                 return tagged_tests
#             else:
#                 raise Exception(f"- error: no method defined to add tests of type {type(tests)}")

#         def get_all_tests_from_file(yml_file):
#             import yaml
#             with open(yml_file) as stream:
#                 data = yaml.safe_load(stream)
#                 if not "tests" in data.keys():
#                     print(f"- WARNING: could not find tests section in file {yml_file}, returning")
#                     return
#                 tests = data["tests"]
#                 print(f"+ File: {yml_file}")
#                 print(f"  + There are {len(tests)} tests in file {yml_file}")

#                 tags = dict()
#                 for test in tests:
#                     for tag in test["tags"]:
#                         if tag in tags.keys():
#                             tags[tag] += 1
#                         else:
#                             tags[tag] = 1

#                 print(f"  + Found {len(tags)} tags associated with the tests in the file")
#                 print(f"  + The tags and number of tests they are associated with are as follows")
#                 for tag in sorted(tags.keys()):
#                     print(f"    + {tag}: {tags[tag]}")

#                 suites = dict()
#                 suites["no-suites"] = 0
#                 for test in tests:
#                     if "suites" in test.keys():
#                         for suite in test["suites"]:
#                             if suite == "no-suites":
#                                 raise Exception("- error: no-suites is a suite, please change the name of key")
#                             if suite in suites.keys():
#                                 suites[suite] += 1
#                             else:
#                                 suites[suite] = 1
#                     else:
#                         suites["no-suites"] += 1

#                 print(f"  + Found {len(suites)} suites associated with tests in the file")
#                 print(f"  + The suites and number of tests they are associated with are as follows")
#                 for suite in sorted(suites.keys()):
#                     print(f"    + {suite}: {suites[suite]}")

#         proj_yml_incl_path = get_yml_file_name_incl_path(local_infra_dir, project_yml)
#         print(f"+ Found {project_yml} at {proj_yml_incl_path}")

#         for yml_file in yml_files:
#             get_all_tests_from_file(get_yml_file_name_incl_path(local_infra_dir, yml_file))

#         tags = get_tags(proj_yml_incl_path, suites, tags)
#         print(f"+ Tags associated with suite {suites} are {tags}")
#         print(f"+ Identifying the tests these tags in given yaml files: {yml_files}")

#         return get_tests(yml_files, tags, local_infra_dir, tests)

#     import os
#     import shutil

#     force           = args["force"]               if "force"               in args.keys() else False
#     hostname        = args["hostname"]            if "hostname"            in args.keys() else None
#     infra_dir       = args["infra_dir"]           if "infra_dir"           in args.keys() else "infra"
#     project_yml     = args["project_yml"]         if "project_yml"         in args.keys() else "project.yml"
#     remote_dir      = args["test_bench_dir"]      if "test_bench_dir"      in args.keys() else "ws-tensix"
#     remote_dir_path = args["test_bench_dir_path"] if "test_bench_dir_path" in args.keys() else None
#     suites          = args["suites"]              if "suites"              in args.keys() else None
#     tags            = args["tags"]                if "tags"                in args.keys() else None
#     tests           = args["tests"]               if "tests"               in args.keys() else None
#     tests_dir       = args["tests_dir"]           if "tests_dir"           in args.keys() else "infra/tensix/rsim/tests"
#     username        = args["username"]            if "username"            in args.keys() else getpass.getuser()
#     yml_files       = args["yml_files"]           if "yml_files"           in args.keys() else []
#     local_rtl_dir   = args["local_ws-tensix_dir"] if "local_ws-tensix_dir" in args.keys() else f"from-{remote_dir}" # todo change this to appropriate key values.

#     if not remote_dir_path:
#         raise Exception("- error: please provide remote dir path")

#     local_infra_dir = os.path.join(local_rtl_dir, infra_dir)

#     if force:
#         if os.path.isdir(local_infra_dir):
#             shutil.rmtree(local_infra_dir)

#     # create the directory if it doesn't exist.
#     if not os.path.isdir(local_rtl_dir):
#         os.makedirs(local_rtl_dir)

#     if not os.path.isdir(local_infra_dir):
#         print(f"+ Copying ws-tensix/infra directory locally")
#         os.chdir(local_rtl_dir)
#         with Connection(hostname, user = username) as conn:
#             remote_dir_incl_path  = os.path.join(remote_dir_path, remote_dir)
#             infra_dir_incl_path   = os.path.join(remote_dir_incl_path, infra_dir)
#             cmd = f"rsync -az {username}@{hostname}:{infra_dir_incl_path} ."
#             print(f"+ Executing command: {cmd}")
#             conn.local(cmd)

#         os.chdir("..")
#     else:
#         print(f"+ Directory {local_infra_dir} exists locally")

#     return get_test_names(suites, yml_files, tags, tests, local_infra_dir, project_yml)

# def get_all_tests_from_yml_files(args):
#     def get_yml_file_name_incl_path(local_infra_dir, yml_file):
#         yml_files = []
#         for pwd, _, files in os.walk(local_infra_dir):
#             if yml_file in files:
#                 yml_files.append(os.path.join(pwd,yml_file))

#         if 0 == len(yml_files):
#             raise Exception(f"- error: could not find {yml_file} in directory {local_infra_dir}")
#         elif 1 == len(yml_files):
#             return yml_files[0]
#         else:
#             msg = f"- error: multiple project yml files found:\n"
#             for ele in yml_files:
#                 msg += f"  - {ele}\n"

#                 msg.rstrip()

#             raise Exception(msg)

#     def get_all_tests_from_file(yml_file):
#         import yaml
#         with open(yml_file) as stream:
#             data = yaml.safe_load(stream)
#             if not "tests" in data.keys():
#                 print(f"- WARNING: could not find tests section in file {yml_file}, returning")
#                 return
#             tests = data["tests"]
#             return set(test["test-name"] for test in tests)

#     import os
#     import shutil

#     force           = args["force"]                if "force"                in args.keys() else False
#     hostname        = args["hostname"]             if "hostname"             in args.keys() else None
#     infra_dir       = args["infra_dir"]            if "infra_dir"            in args.keys() else "infra"
#     project_yml     = args["project_yml"]          if "project_yml"          in args.keys() else "project.yml"
#     remote_dir      = args["test_bench_dir"]       if "test_bench_dir"       in args.keys() else "ws-tensix"
#     remote_dir_path = args["test_bench_dir_path"]  if "test_bench_dir_path"  in args.keys() else None
#     suites          = args["suites"]               if "suites"               in args.keys() else None
#     tags            = args["tags"]                 if "tags"                 in args.keys() else None
#     tests_dir       = args["tests_dir"]            if "tests_dir"            in args.keys() else "infra/tensix/rsim/tests"
#     username        = args["username"]             if "username"             in args.keys() else getpass.getuser()
#     yml_files       = args["yml_files"]            if "yml_files"            in args.keys() else []
#     local_rtl_dir   = args["local_test_bench_dir"] if "local_test_bench_dir" in args.keys() else f"from-{remote_dir}" # todo change this to appropriate key values.

#     if not remote_dir_path:
#         raise Exception("- error: please provide remote dir path")

#     local_infra_dir = os.path.join(local_rtl_dir, infra_dir)

#     if force:
#         if os.path.isdir(local_infra_dir):
#             shutil.rmtree(local_infra_dir)

#     # create the directory if it doesn't exist.
#     if not os.path.isdir(local_rtl_dir):
#         os.makedirs(local_rtl_dir)

#     if not os.path.isdir(local_infra_dir):
#         print(f"+ Copying ws-tensix/infra directory locally")
#         os.chdir(local_rtl_dir)
#         with Connection(hostname, user = username) as conn:
#             remote_dir_incl_path  = os.path.join(remote_dir_path, remote_dir)
#             infra_dir_incl_path   = os.path.join(remote_dir_incl_path, infra_dir)
#             cmd = f"rsync -az {username}@{hostname}:{infra_dir_incl_path} ."
#             print(f"+ Executing command: {cmd}")
#             conn.local(cmd)

#         os.chdir("..")
#     else:
#         print(f"+ Directory {local_infra_dir} exists locally")

#     tests = set()
#     for yml_file in yml_files:
#         tests.update(get_all_tests_from_file(get_yml_file_name_incl_path(local_infra_dir, yml_file)))

#     return sorted(tests)

# def get_rtl_test_names(args):
#     tests = []
#     if "suites" == args["test_mode"]:
#         tests = get_test_names_from_rtl_test_bench(args)
#     elif "all" == args["test_mode"]:
#         tests = get_all_tests_from_yml_files(args)
#     else:
#         raise Exception(f"- errror: no method defined to get names of tests from test mode: {args['test_mode']}")

#     return tests

#     # print(f"- found {len(tests)} based on tests, tags, suites, yml_files and test_mode = {args["test_mode"]}")


#     # new_tests = []
#     # for test in tests:
#     #     if test.

#     # return None

def get_tensix_instructions_file_from_rtl_test_bench(args):
    import os

    if os.path.exists(args["instructions_dir"]):
        print(f"- moving local {args['instructions_dir']} to {args["instructions_dir"] + "_prev"}")
        os.system(f"rm -rf {args['instructions_dir']}_prev")
        os.system(f"mv {args['instructions_dir']} {args['instructions_dir']}_prev")

    hostname = args["hostname"]
    username = args["username"]
    instructions_dir = os.path.join(args["test_bench_dir_path"], args["test_bench_dir"], args["instructions_dir_path"], args["instructions_dir"])

    local_instr_set_dir = os.path.join(args["local_test_bench_dir"], args["instructions_dir_path"])

    print("+ Remote instructions set directory: ", instructions_dir)
    print("+ Local instructions set directory: ", local_instr_set_dir)

    if os.path.exists(local_instr_set_dir):
        print(f"- moving local {local_instr_set_dir} to {local_instr_set_dir + "_prev"}")
        os.system(f"rm -rf {local_instr_set_dir}_prev")
        os.system(f"mv {local_instr_set_dir} {local_instr_set_dir}_prev")

    os.makedirs(local_instr_set_dir)

    with fabric.Connection(hostname, user = username) as conn:
        if conn.run(f"test -d {instructions_dir}", warn=True).failed:
            raise Exception(f"- error: could not find {instructions_dir} on remote machine {hostname}")

        print(f"+ Copying instruction set directory from remote server to local directory at {local_instr_set_dir}")
        cmd = f"rsync -az --progress {username}@{hostname}:{instructions_dir} {local_instr_set_dir}"
        print(f"+ Executing command: {cmd}")
        conn.local(cmd)

def execute_rtl_test(test, hostname, username, remote_dir_path, remote_dir, debug_dir, test_dir_suffix, log_file_suffix, warn_flag):
        import os

        with fabric.Connection(hostname, user = username) as conn:
            root_dir = os.path.join(remote_dir_path, remote_dir)
            log_file = test + log_file_suffix # todo: replace this with rtl_args dict entry.
            log_file_dir = os.path.join(root_dir, debug_dir, test + test_dir_suffix)
            log_file = os.path.join(log_file_dir, log_file)
            print(log_file)

            with conn.cd(root_dir):
                cmds = []
                cmds.append(f"cd {root_dir}")
                cmds.append(f"pwd")
                cmds.append(f"make submod-sync")
                cmds.append(f"source .condasetup")
                # cmds.append(f"source SETUP.cctb.sh")
                cmds.append(f"source SETUP.cctb.local.sh")
                cmds.append(f"mkdir -p {log_file_dir}")
                cmds.append(f"rsim run_test --test {test} > {log_file} 2>&1")

                cmd = f"ssh -X localhost -p 2224 '{" && ".join(cmds)}'"
                print(f"- executing: {cmd}")
                result = conn.run(cmd, warn = warn_flag, pty = True)

                return {
                    "test"      : test,
                    "stdout"    : result.stdout.strip(),
                    "stderr"    : result.stderr.strip(),
                    "exit_code" : result.exited
                    }

def copy_rtl_test_data(test, hostname, username, remote_dir_path, remote_dir, debug_dir, test_dir_suffix, local_test_data_dir):
    # print(f"copy rtl test data. test: {test}")
    with fabric.Connection(hostname, user = username) as conn:
        debug_dir_incl_path = os.path.join(remote_dir_path, remote_dir, debug_dir)
        test_dir = f"{test}{test_dir_suffix}"
        test_dir_incl_path = os.path.join(debug_dir_incl_path, test_dir)

        cmd = f"rsync -az {username}@{hostname}:{test_dir_incl_path} {local_test_data_dir}"
        print(f"+ Executing command {cmd}")
        conn.local(cmd)

def execute_rtl_tests(tests, args):
    import os

    hostname        = args["hostname"]            if "hostname"            in args.keys() else None
    remote_dir_path = args["test_bench_dir_path"] if "test_bench_dir_path" in args.keys() else None
    force           = args["force"]               if "force"               in args.keys() else False
    num_processes   = args["num_processes"]       if "num_processes"       in args.keys() else 1
    username        = args["username"]            if "username"            in args.keys() else getpass.getuser()
    remote_dir      = args["test_bench_dir"]      if "test_bench_dir"      in args.keys() else "ws-tensix"
    debug_dir       = args["debug_dir"]           if "debug_dir"           in args.keys() else "rsim/debug"
    test_dir_suffix = args["test_dir_suffix"]     if "test_dir_suffix"     in args.keys() else "_0"
    sim_result_yml  = args["sim_result_yml"]      if "sim_result_yml"      in args.keys() else "sim_result.yml"
    log_file_suffix = args["rtl_log_file_suffix"] if "rtl_log_file_suffix" in args.keys() else ".rtl_test.log"
    local_test_data_dir = args["local_test_bench_dir"] if "local_test_bench_dir" in args.keys() else f"from-{remote_dir}"
    local_test_data_dir = os.path.join(local_test_data_dir, debug_dir)

    # checks for hostname, remote_dir_path
    if not hostname:
        raise Exception("- error: please provide hostname")

    if not username:
        raise Exception("- error: please provide username")

    if not remote_dir_path:
        raise Exception("- error: please provide remote dir path")

    if num_processes < 1:
        print(f"- setting number of processes to 1, given value was: {num_processes}")
        num_processes = 1

    if not os.path.isdir(local_test_data_dir):
        print(f"+ Local directory {local_test_data_dir} does not exist, creating it")
        os.makedirs(local_test_data_dir)
    else:
        print(f"+ Local directory {local_test_data_dir} exists")

    if not os.path.isdir(local_test_data_dir):
        raise Exception(f"- error: could not create {local_test_data_dir} directory")

    tests_to_execute = []
    with fabric.Connection(hostname, user = username) as conn:
        root_dir = os.path.join(remote_dir_path, remote_dir)

        if conn.run(f"test -d {root_dir}", warn=True).failed:
            raise Exception(f"- error: could not find {root_dir} on remote server ({hostname})")

        with conn.cd(root_dir):
            tests_to_execute = []
            if force:
                tests_to_execute = tests
            else:
                for test in tests:
                    sim_result_yml_incl_path = os.path.join(root_dir, debug_dir, test + test_dir_suffix, sim_result_yml)

                    if conn.run(f"test -f {sim_result_yml_incl_path}", warn=True).failed:
                        tests_to_execute.append(test)

    print("- Number of RTL tests:            ", len(tests))
    print("- Number of RTL tests to execute: ", len(tests_to_execute))

    test_results = []

    if len(tests_to_execute):
        warn_flag = True # move to next test if this fails.

        num_processes = min(num_processes, len(tests_to_execute))

        print(f"- Number of parallel processes to execute RTL tests: {num_processes}")

        with multiprocessing.Pool(processes = num_processes) as pool:
            # pool.map(functools.partial(execute_rtl_test, hostname = hostname, username = username, remote_dir_path = remote_dir_path, remote_dir = remote_dir, warn_flag = warn_flag), tests_to_execute)
            test_results = pool.starmap(execute_rtl_test, [(test, hostname, username, remote_dir_path, remote_dir, debug_dir, test_dir_suffix, log_file_suffix, warn_flag) for test in tests_to_execute])

    num_processes = min(num_processes, len(tests))
    print(f"- Number of parallel processes to copy RTL test data: {num_processes}")

    with multiprocessing.Pool(processes = num_processes) as pool:
        test_data_copy_results = pool.starmap(copy_rtl_test_data, [(test, hostname, username, remote_dir_path, remote_dir, debug_dir, test_dir_suffix, local_test_data_dir) for test in tests])

    return test_results

def execute_t3sim_test(test, t3sim_args):
    binutils_dir = t3sim_args["binutils_dir"] if "binutils_dir" in t3sim_args.keys() else "binutils-playground"
    t3sim_dir    = t3sim_args["sim_dir"]      if "sim_dir"      in t3sim_args.keys() else "t3sim"

    import os
    import sys
    sys.path.append(f'./{t3sim_dir}')
    sys.path.append(f'{os.path.join(t3sim_dir, binutils_dir, "py")}')
    import read_elf
    import subprocess
    import tensix

    def get_num_dirs_with_keyword(path, keyword):
        import os
        os_walk = os.walk(path)

        for pwd, sub_dirs, files in os_walk:
            if any(sub_dir.startswith(keyword) for sub_dir in sub_dirs):
                kw_dirs = []
                for sub_dir in sub_dirs:
                    if sub_dir.startswith(keyword):
                        kw_dirs.append(sub_dir)

                kw_dirs = sorted(kw_dirs)
                kw_ids = sorted(int(kw_dir.split('_')[-1]) for kw_dir in kw_dirs)
                min_kw_id = min(kw_ids)
                if 0 != min_kw_id:
                    raise Exception(f"- error: neo cores do not start from 0. kw_dirs are as follows: {kw_dirs}")

                if kw_ids == list(range(min(kw_ids), max(kw_ids) + 1)):
                    return len(kw_ids)
                else:
                    raise Exception(f"- error: found non-continuous directories: {kw_dirs}")

    def get_num_neos(path):
        return get_num_dirs_with_keyword(path, "neo_")

    def get_num_threads(path):
        return get_num_dirs_with_keyword(path, "thread_")

    def get_input_cfg(test_name, debug_dir, cfg_dir, start_function = "main"):
        import os
        input_cfg_dict = dict()

        input_cfg_dict.update({"input" : dict()})
        input_cfg_dict.update({"description" : dict()})

        input_cfg = input_cfg_dict["input"]

        input_cfg.update({"syn" : 0}) # this is not a synthetic test

        test_dir = test_name + "_0"
        input_cfg.update({"name" : test_name})

        if not debug_dir.endswith(test_dir):
            test_dir = os.path.join(os.getcwd(), debug_dir, test_dir)
        else:
            test_dir = debug_dir

        num_neos = get_num_neos(test_dir)

        if 1 != num_neos:
            raise Exception(f"- expected only 1 neo core to be present, found: {num_neos}. test: {test_name}, test_dir: {test_dir}")

        os_walk = os.walk(test_dir)

        for neo_id in range(num_neos):
            neo_dir = f"neo_{neo_id}"
            for pwd, _, _ in os_walk:
                if pwd.endswith(neo_dir):
                    num_threads = get_num_threads(pwd)
                    if num_threads in {0, None}:
                        raise Exception(f"- error: expected at least one thread, received {num_threads}. Path: {pwd}")

                    input_cfg.update({"numThreads" : num_threads})

                    neo_os_walk = os.walk(pwd)
                    for pwd1, _, files in neo_os_walk:
                        for file in files:
                            if file.endswith(".elf"):
                                thread_id = number = int(file.split("_")[-1].split(".")[0])
                                if thread_id > num_threads:
                                    raise Exception(f"- error: thread id is greater than number of threads. thread_id: {thread_id}, number of threads: {num_threads}")
                                input_cfg.update({f"th{thread_id}Path" : pwd1})
                                input_cfg.update({f"th{thread_id}Elf" : file})

        if "dvalid" in test_name:
            msg = f"{test_name} contains dvalid.\n"
            msg += "in the inputcfg we are going to make the following changes.\n"
            msg += "1. check that it has 3 threads, change it to 4 threads\n"
            msg += "1. move thread 2 path and files to thread 3\n"
            msg += "1. leave thread 2 empty\n"

            print(msg)

            if 3 != input_cfg["numThreads"]:
                raise Exception(f"- error: expected numThreads to be 3, received {input_cfg['numThreads']}")

            input_cfg["numThreads"] = 4 # change it to 4.

            # add thread 3
            thread_id = 3
            input_cfg[f"th3Path"] = input_cfg[f"th2Path"]
            input_cfg[f"th3Elf"]  = input_cfg[f"th2Elf"]

            # make thread 2 empty
            input_cfg[f"th2Path"] = ""
            input_cfg[f"th2Elf"]  = ""

        input_cfg.update({"startFunction" : start_function})

        # t3sim.print_json(input_cfg_dict, f"t3sim_inputcfg_{test_name}.json")
        # print("**************** file to write: ", file_name)
        file_name = os.path.join(cfg_dir, f"t3sim_inputcfg_{test_name}.json")
        with open(file_name, 'w') as file:
            json.dump(input_cfg_dict, file, indent = 2)

        return input_cfg_dict

    def get_cfg(test_name, debug_dir, cfg_dir, mop_base_addr_str, cfg_base_addr_str, cfg_offset, enable_sync = 1, delay = 10, max_num_threads = 4):
        import os

        def get_tensix_instruction_kind(test_dir):
            if not os.path.exists(test_dir):
                raise Exception(f"- error: {test_dir} does not exist. AAAA")

            os_walk = os.walk(test_dir)
            ttx_kinds = set()
            for pwd, _, files in os_walk:
                for file in files:
                    if file.endswith(".elf"):
                        for kind in read_elf.get_instruction_kinds(os.path.join(pwd, file)):
                            if kind.is_tensix():
                                ttx_kinds.add(kind)

            if 1 != len(ttx_kinds):
                import decoded_instruction
                return decoded_instruction.instruction_kind.ttqs
                # raise Exception(f"- error: expected one tensix instruction kind, received {len(ttx_kinds)}, kinds: {ttx_kinds}")
            else:
                return list(ttx_kinds)[0]

        def update_engines(engines, delay, cfg):
            cfg_engines_value = []
            for engine, instructions in engines.items():
                ele = dict()
                ele.update({"engineName"         : engine})
                ele.update({"engineInstructions" : instructions})
                ele.update({"delay"              : delay})

                cfg_engines_value.append(ele)

            cfg.update({"engines" : cfg_engines_value})

        def update_unpacker_engines (cfg):
            import re
            def get_engine_idx(engine_name, cfg):
                for idx, engine in enumerate(cfg["engines"]):
                    if engine["engineName"] == engine_name:
                        return idx

                return len(cfg["engines"])

            def get_unpacker_engine_ids (cfg):
                ids = set()
                for engine in cfg["engines"]:
                    if "UNPACK" == engine["engineName"]:
                        for instruction in engine["engineInstructions"]:
                            match = re.search(r'\d+', instruction)  # Find first occurrence of a number
                            if match:
                                ids.add(int(match.group()))

                return ids if len(ids) else None

            unpack_idx = get_engine_idx("UNPACK", cfg)
            ids = get_unpacker_engine_ids(cfg)

            for id in ids:
                engine_name = f"UNPACKER{id}"
                engine_instructions = []
                for instruction in cfg["engines"][unpack_idx]["engineInstructions"]:
                    match = re.search(r'\d+', instruction)  # Find first occurrence of a number
                    if match:
                        if int(match.group()) == id:
                            engine_instructions.append(instruction)
                    else:
                        engine_instructions.append(instruction)

                new_engine = dict()
                new_engine["engineName"] = engine_name
                new_engine["engineInstructions"] = engine_instructions
                new_engine["engineGrp"] = engine_name[:-1]
                new_engine["delay"] = delay

                cfg["engines"].append(new_engine)

            del cfg["engines"][unpack_idx]

        def update_packer_engines (cfg):
            import re
            def get_engine_idx(engine_name, cfg):
                for idx, engine in enumerate(cfg["engines"]):
                    if engine["engineName"] == engine_name:
                        return idx

                return len(cfg["engines"])

            def get_packer_engine_ids (cfg):
                ids = set()
                for engine in cfg["engines"]:
                    if "PACK" == engine["engineName"]:
                        for instruction in engine["engineInstructions"]:
                            match = re.search(r'\d+', instruction)  # Find first occurrence of a number
                            if match:
                                ids.add(int(match.group()))

                return ids if len(ids) else None

            pack_idx = get_engine_idx("PACK", cfg)
            ids = get_packer_engine_ids(cfg)

            for id in ids:
                engine_name = f"PACKER{id}"
                engine_instructions = []
                for instruction in cfg["engines"][pack_idx]["engineInstructions"]:
                    match = re.search(r'\d+', instruction)  # Find first occurrence of a number
                    if match:
                        if int(match.group()) == id:
                            engine_instructions.append(instruction)
                    else:
                        engine_instructions.append(instruction)

                new_engine = dict()
                new_engine["engineName"] = engine_name
                new_engine["engineInstructions"] = engine_instructions
                new_engine["engineGrp"] = engine_name[:-1]
                new_engine["delay"] = delay

                cfg["engines"].append(new_engine)

            del cfg["engines"][pack_idx]

        def update_mop_cfg_start(base_addr_str, max_num_threads, cfg):
            # value = dict()
            # for id in range(max_num_threads):
            #     value.update({str(id) : base_addr_str})

            # cfg.update({"MOP_CFG_START" : value})

            cfg.update({"MOP_CFG_START" : base_addr_str})

        def update_cfg_start(base_addr_str, cfg):
            cfg.update({"CFG_START" : base_addr_str})

        def add_engineGrp_to_engines(cfg):
            for engine in cfg["engines"]:
                engine_grp = None
                if engine["engineName"].startswith("UNPACKER"):
                    engine_grp = "UNPACK"
                elif engine["engineName"].startswith("PACKER"):
                    engine_grp = "PACK"
                elif ("INSTRISSUE" == engine["engineName"]) or ("INSTISSUE" == engine["engineName"]):
                    engine_grp = "MATH"
                else:
                    engine_grp = engine["engineName"]

                engine["engineGrp"] = engine_grp

        def update_stack(cfg):
            value = dict()

            value.update({"0": ["0x8023FF", "0x802000"]})
            value.update({"1": ["0x801FFF", "0x801C00"]})
            value.update({"2": ["0x801BFF", "0x801800"]})
            value.update({"3": ["0x8017FF", "0x801400"]})

            cfg.update({"stack" : value})

        test_dir = test_name + "_0"

        if not debug_dir.endswith(test_dir):
            test_dir = os.path.join(os.getcwd(), debug_dir, test_dir)
        else:
            test_dir = debug_dir

        instruction_kind = get_tensix_instruction_kind(test_dir)

        cfg_dict = dict()

        cfg_dict.update({"enableSync"    : enable_sync})
        cfg_dict.update({"arch"          : instruction_kind.name})
        cfg_dict.update({"numTriscCores" : get_num_neos(test_dir)})
        cfg_dict.update({"orderScheme"   : [ [0,1], [0,1], [0,1,2], [1,2] ]})

        update_engines(tensix.get_execution_engines_and_instructions(instruction_kind), delay, cfg_dict)
        update_unpacker_engines(cfg_dict)
        update_packer_engines(cfg_dict)
        add_engineGrp_to_engines(cfg_dict)
        update_mop_cfg_start(mop_base_addr_str, max_num_threads, cfg_dict)
        update_cfg_start(cfg_base_addr_str, cfg_dict)
        cfg_dict.update({"CFG_OFFSET" : cfg_offset})
        # update_stack(test_dir, cfg_dict)
        update_stack(cfg_dict)

        # t3sim.print_json(cfg_dict, f"t3sim_cfg_{test}.json")
        file_name = os.path.join(cfg_dir, f"t3sim_cfg_{test}.json")
        with open(file_name, "w") as file:
            json.dump(cfg_dict, file, indent = 2)

        return cfg_dict

    t3sim_dir                    = t3sim_args["sim_dir"]                       if "sim_dir"                      in t3sim_args.keys() else "t3sim"
    logs_dir                     = t3sim_args["logs_dir"]                      if "logs_dir"                     in t3sim_args.keys() else "logs"
    debug_dir                    = t3sim_args["debug_dir"]                     if "debug_dir"                    in t3sim_args.keys() else ""
    binutils_dir                 = t3sim_args["binutils_dir"]                  if "binutils_dir"                 in t3sim_args.keys() else "binutils-playground"
    start_function               = t3sim_args["start_function"]                if "start_function"               in t3sim_args.keys() else "main"
    delay                        = t3sim_args["delay"]                         if "delay"                        in t3sim_args.keys() else 10
    max_num_threads_per_neo_core = t3sim_args["max_num_threads_per_neo_core"]  if "max_num_threads_per_neo_core" in t3sim_args.keys() else 4
    enable_sync                  = t3sim_args["enable_sync"]                   if "enable_sync"                  in t3sim_args.keys() else 1
    cfg_dir                      = t3sim_args["cfg_dir"]                       if "cfg_dir"                      in t3sim_args.keys() else "cfg"
    log_file_suffix              = t3sim_args["t3sim_log_file_suffix"]         if "t3sim_log_file_suffix"        in t3sim_args.keys() else ".t3sim_test.log"

    if "mop_base_addr_str" not in t3sim_args.keys():
        raise Exception("- error: could not find mop_base_addr_str in t3sim_args")

    if "cfg_base_addr_str" not in t3sim_args.keys():
        raise Exception("- error: could not find cfg_base_addr_str in t3sim_args")

    mop_base_addr_str = t3sim_args["mop_base_addr_str"]
    cfg_base_addr_str = t3sim_args["cfg_base_addr_str"]
    cfg_offset        = t3sim_args["cfg_offset"]

    cfg_dir_incl_path = os.path.join(t3sim_dir, cfg_dir)

    get_cfg(test, debug_dir, cfg_dir_incl_path, mop_base_addr_str, cfg_base_addr_str, cfg_offset, enable_sync, delay, max_num_threads_per_neo_core)
    get_input_cfg(test, debug_dir, cfg_dir_incl_path, start_function)

    os.chdir(t3sim_dir)
    log_file_name = f"{test}{log_file_suffix}"
    cmd = f"python t3sim.py --cfg {cfg_dir}/t3sim_cfg_{test}.json --inputcfg {cfg_dir}/t3sim_inputcfg_{test}.json"
    print(f"Executing t3sim test: {test}")
    file = open(log_file_name, 'w')
    subprocess.call(cmd.split(), stdout = file, stderr = subprocess.STDOUT)
    os.chdir("..")

def execute_t3sim_tests(tests, t3sim_args = None, rtl_args = None):

    import filecmp
    import os
    import shutil

    t3sim_dir                    = t3sim_args["sim_dir"]                       if "sim_dir"                      in t3sim_args.keys() else "t3sim"
    logs_dir                     = t3sim_args["logs_dir"]                      if "logs_dir"                     in t3sim_args.keys() else "logs"
    # elf_files_dir                = t3sim_args["elf_files_dir"]                 if "elf_files_dir"                in t3sim_args.keys() else "debug"
    git_repo                     = t3sim_args["git"]                           if "git"                          in t3sim_args.keys() else "git@github.com:vmgeorgeTT/t3sim.git"
    binutils_git_repo            = t3sim_args["binutils_git"]                  if "binutils_git"                 in t3sim_args.keys() else "git@github.com:jajuTT/binutils-playground.git"
    force                        = t3sim_args["force"]                         if "force"                        in t3sim_args.keys() else False
    num_processes                = t3sim_args["num_processes"]                 if "num_processes"                in t3sim_args.keys() else 1
    json_log_prefix              = t3sim_args["json_log_prefix"]               if "json_log_prefix"              in t3sim_args.keys() else "simreport_"
    json_log_suffix              = t3sim_args["json_log_suffix"]               if "json_log_suffix"              in t3sim_args.keys() else ".json"
    # test_dir_suffix              = t3sim_args["test_dir_suffix"]               if "test_dir_suffix"              in t3sim_args.keys() else "_0"
    # start_function               = t3sim_args["start_function"]                if "start_function"               in t3sim_args.keys() else "main"
    # delay                        = t3sim_args["delay"]                         if "delay"                        in t3sim_args.keys() else 10
    # max_num_threads_per_neo_core = t3sim_args["max_num_threads_per_neo_core"]  if "max_num_threads_per_neo_core" in t3sim_args.keys() else 4
    # enable_sync                  = t3sim_args["enable_sync"]                   if "enable_sync"                  in t3sim_args.keys() else 1
    t3sim_branch                 = t3sim_args["branch"]                        if "branch"                       in t3sim_args.keys() else "main"
    binutils_dir                 = binutils_git_repo.split("/")[-1][:-4]
    t3sim_args["binutils_dir"]   = binutils_dir

    def copy_remote_dir_to_local(remote_dir, remote_dir_path, remote_root_dir, local_root_dir, hostname, username):
        remote_path = os.path.join(remote_root_dir, remote_dir_path, remote_dir)
        local_path  = os.path.join(local_root_dir, remote_dir_path)

        if not os.path.isdir(local_path):
            os.makedirs(local_path)

        with fabric.Connection(hostname, user = username) as conn:
            if conn.run(f"test -d {remote_path}", warn=True).failed:
                raise Exception(f"- error: could not find {remote_path} on remote machine {hostname}")

            print(f"+ Copying {remote_path} directory from remote server to local directory at {local_path}")
            cmd = f"rsync -az --progress {username}@{hostname}:{remote_path} {local_path}"
            print(f"+ Executing command: {cmd}")
            conn.local(cmd)

    def copy_src_hd_proj_dir_from_remote(rtl_args):
        local_root_dir  = rtl_args["local_test_bench_dir"]
        remote_dir      = rtl_args["src_hd_proj_dir"] # directory to copy
        remote_dir_path = rtl_args["src_hd_proj_dir_path"]
        remote_root_dir = os.path.join(rtl_args["test_bench_dir_path"], rtl_args["test_bench_dir"])
        hostname        = rtl_args["hostname"]
        username        = rtl_args["username"]

        copy_remote_dir_to_local(remote_dir, remote_dir_path, remote_root_dir, local_root_dir, hostname, username)

    def copy_src_firmware_dir_from_remote(rtl_args):
        local_root_dir  = rtl_args["local_test_bench_dir"]
        remote_dir      = rtl_args["src_firmware_dir"] # directory to copy
        remote_dir_path = rtl_args["src_firmware_dir_path"]
        remote_root_dir = os.path.join(rtl_args["test_bench_dir_path"], rtl_args["test_bench_dir"])
        hostname        = rtl_args["hostname"]
        username        = rtl_args["username"]

        copy_remote_dir_to_local(remote_dir, remote_dir_path, remote_root_dir, local_root_dir, hostname, username)

    def get_address_from_define(path, file, name):
        # file: <file>
        #   #define <name> <addr>
        # returns addr
        start_string = f"#define {name}"

        addr = set()
        for pwd, _, files in os.walk(path):
            for f in files:
                if f == file:
                    file_incl_path = os.path.join(pwd, file)
                    with open(file_incl_path, 'r') as fp:
                        for line in fp:
                            line = line.strip()
                            if line.startswith(start_string):
                                addr.add(line.split()[-1])

        # TODO: make sure we find mop_cfg_base address in each of the subdirectories in `proj`

        if 0 == len(addr):
            raise Exception(f"- error: could not find string {start_string} in file {file} in directory {path}")
        elif 1 != len(addr):
            raise Exception(f"- error: expected one addr address value, received {len(addr)}. The values are: {addr}")

        return list(addr)[0]

    def get_MOP_CFG_BASE_address(rtl_args):
        name = "MOP_CFG_BASE"
        file = "tt_t6_trisc_map.h"
        path = os.path.join(rtl_args["local_test_bench_dir"], rtl_args["src_hd_proj_dir_path"], rtl_args["src_hd_proj_dir"])

        return get_address_from_define(path, file, name)

    def get_CFG_REGS_BASE(rtl_args):
        name = "CFG_REGS_BASE"
        file = "tt_t6_trisc_map.h"
        path = os.path.join(rtl_args["local_test_bench_dir"], rtl_args["src_hd_proj_dir_path"], rtl_args["src_hd_proj_dir"])

        return get_address_from_define(path, file, name)

    def get_TENSIX_CFG_BASE(rtl_args):
        name = "TENSIX_CFG_BASE"
        file = "tensix.h"
        path = os.path.join(rtl_args["local_test_bench_dir"], rtl_args["src_firmware_dir_path"], rtl_args["src_firmware_dir"])
        addr = get_address_from_define(path, file, name)
        if "CFG_REGS_BASE" == addr:
            return get_CFG_REGS_BASE(rtl_args)
        else:
            raise Exception(f"- error: expected {name} address to be associated with CFG_REGS_BASE but received {addr}")

    def get_CFG_OFFSET(rtl_args):
        cfg_offset_keys = { # t3sim name : rtl name
            "DEST_TARGET_REG_CFG_MATH_SEC0_OFFSET_ADDR32" : "DEST_TARGET_REG_CFG_MATH_SEC0_Offset_ADDR32",
            "DEST_TARGET_REG_CFG_MATH_SEC1_OFFSET_ADDR32" : "DEST_TARGET_REG_CFG_MATH_SEC1_Offset_ADDR32",
            "DEST_TARGET_REG_CFG_MATH_SEC2_OFFSET_ADDR32" : "DEST_TARGET_REG_CFG_MATH_SEC2_Offset_ADDR32",
            "DEST_TARGET_REG_CFG_MATH_SEC3_OFFSET_ADDR32" : "DEST_TARGET_REG_CFG_MATH_SEC3_Offset_ADDR32",
            "DEST_DVALID_CTRL_UNPACKER" : [
                "UNPACK_TO_DEST_DVALID_CTRL_disable_auto_bank_id_toggle_ADDR32",
                "UNPACK_TO_DEST_DVALID_CTRL_toggle_mask_ADDR32",
                "UNPACK_TO_DEST_DVALID_CTRL_wait_mask_ADDR32",
                "UNPACK_TO_DEST_DVALID_CTRL_wait_polarity_ADDR32"
                ],
            "DEST_DVALID_CTRL_MATH" : [
                "MATH_DEST_DVALID_CTRL_disable_auto_bank_id_toggle_ADDR32",
                "MATH_DEST_DVALID_CTRL_toggle_mask_ADDR32",
                "MATH_DEST_DVALID_CTRL_wait_mask_ADDR32",
                "MATH_DEST_DVALID_CTRL_wait_polarity_ADDR32"
                ],
            "DEST_DVALID_CTRL_SFPU" : [
                "SFPU_DEST_DVALID_CTRL_disable_auto_bank_id_toggle_ADDR32",
                "SFPU_DEST_DVALID_CTRL_toggle_mask_ADDR32",
                "SFPU_DEST_DVALID_CTRL_wait_mask_ADDR32",
                "SFPU_DEST_DVALID_CTRL_wait_polarity_ADDR32"
                ],
            "DEST_DVALID_CTRL_PACKER" : [
                "PACK_DEST_DVALID_CTRL_disable_auto_bank_id_toggle_ADDR32",
                "PACK_DEST_DVALID_CTRL_toggle_mask_ADDR32",
                "PACK_DEST_DVALID_CTRL_wait_mask_ADDR32",
                "PACK_DEST_DVALID_CTRL_wait_polarity_ADDR32"
                ]
        }

        file = "cfg_defines.h"
        path = os.path.join(rtl_args["local_test_bench_dir"], rtl_args["src_hd_proj_dir_path"], rtl_args["src_hd_proj_dir"])

        cfg_offsets = dict() # t3sim_name : offset
        for key, rtl_names in cfg_offset_keys.items():
            if isinstance(rtl_names, str):
                cfg_offsets[key] = int(get_address_from_define(path, file, rtl_names))
            elif isinstance(rtl_names, list):
                offsets = set()
                for name in rtl_names:
                    offsets.add(get_address_from_define(path, file, name))

                if 0 == len(offsets):
                    raise Exception(f"- error: could not find offset for {rtl_names} in file {file} in directory {path}")
                elif 1 != len(offsets):
                    raise Exception(f"- error: found multiple offsets for {rtl_names} in file {file} in directory {path}, expected the offset to be same for all the macros. offsets: {offsets}")

                cfg_offsets[key] = int(list(offsets)[0])
            else:
                raise Exception(f"- error: no method defined in function get_CFG_OFFSET to parse input of type {type(rtl_names)}")

        if len(cfg_offset_keys) != len(cfg_offset_keys):
            raise Exception("- error: length mismatch between cfg keys and offsets")

        return cfg_offsets

    def update_tensix_assembly_yaml(assembly_yaml, binutils_dir, instructions_kind, rtl_args):
        binutils_assembly_yaml_dir = os.path.join(binutils_dir, "instruction_sets", instructions_kind)
        binutils_assembly_yaml     = os.path.join(binutils_assembly_yaml_dir, assembly_yaml)

        if not os.path.exists(binutils_assembly_yaml_dir):
            raise Exception(f"- error: directory {binutils_assembly_yaml_dir} does not exist!")

        local_instructions_dir = os.path.join(rtl_args["local_test_bench_dir"], rtl_args["instructions_dir_path"], rtl_args["instructions_dir"])

        if not os.path.isdir(local_instructions_dir):
            get_tensix_instructions_file_from_rtl_test_bench(rtl_args)

        if not os.path.isdir(local_instructions_dir):
            raise Exception(f"- error: could not find directory {local_instructions_dir}")

        found_assembly_yaml = False
        os_walk = os.walk(local_instructions_dir)
        for pwd, _, files in os_walk:
            for file in files:
                if assembly_yaml == file:
                    file_incl_path = os.path.join(os.getcwd(), pwd, file)
                    cond1 = os.path.exists(binutils_assembly_yaml) and (not filecmp.cmp(file_incl_path, binutils_assembly_yaml))
                    cond2 = not os.path.exists(binutils_assembly_yaml)
                    found_assembly_yaml = True
                    if cond1 or cond2:
                        print(f"+ Updating {assembly_yaml}")
                        pwd = os.getcwd()
                        os.chdir(binutils_assembly_yaml_dir)
                        prev_assembly_yaml = f"{assembly_yaml}_prev"
                        if os.path.exists(prev_assembly_yaml):
                            os.remove(prev_assembly_yaml)
                        if os.path.exists(assembly_yaml):
                            shutil.move(assembly_yaml, prev_assembly_yaml)
                        shutil.copy(file_incl_path, ".")
                        os.chdir(pwd)

                    break

        if not found_assembly_yaml:
            raise Exception(f"- error: could not find {assembly_yaml} in local directory {local_instructions_dir}")

    copy_src_hd_proj_dir_from_remote(rtl_args)
    copy_src_firmware_dir_from_remote(rtl_args)
    t3sim_args["mop_base_addr_str"] = get_MOP_CFG_BASE_address(rtl_args)
    t3sim_args["cfg_base_addr_str"] = get_TENSIX_CFG_BASE(rtl_args)
    t3sim_args["cfg_offset"]        = get_CFG_OFFSET(rtl_args)

    if force or (not os.path.isdir(t3sim_dir)):
        if os.path.isdir(t3sim_dir):
            shutil.rmtree(t3sim_dir)

        cmd = f"git clone {git_repo} && cd {t3sim_dir} && git checkout {t3sim_branch} && cd .."
        print(f"- executing command: {cmd}")
        os.system(f"{cmd}")

    if not os.path.isdir(t3sim_dir):
        raise Exception(f"- error: could not find directory {t3sim_dir}")

    if not os.path.isdir(os.path.join(t3sim_dir, binutils_dir)):
        cmd = f"cd {t3sim_dir} && git clone {binutils_git_repo} && cd -"
        print(f"- executing command: {cmd}")
        os.system(f"{cmd}")

    if not os.path.isdir(os.path.join(t3sim_dir, logs_dir)):
        cmd = f"cd {t3sim_dir} && mkdir -p {logs_dir} && cd -"
        print(f"- executing command: {cmd}")
        os.system(f"{cmd}")

    tests_to_execute = []
    for test in tests:
        log_file = json_log_prefix + test + json_log_suffix
        log_file_incl_path = os.path.join(t3sim_dir, logs_dir, log_file)
        if not os.path.isfile(log_file_incl_path):
            tests_to_execute.append(test)

    print("- Number of t3sim tests:            ", len(tests))
    print("- Number of t3sim tests to execute: ", len(tests_to_execute))

    test_results = []

    if len(tests_to_execute):

        update_tensix_assembly_yaml(t3sim_args["assembly_yaml"], os.path.join(t3sim_dir, binutils_dir), t3sim_args["tensix_instructions_kind"], rtl_args)

        num_processes = min(num_processes, len(tests_to_execute))

        print(f"- Number of parallel processes to execute t3sim tests: {num_processes}")

        with multiprocessing.Pool(processes = num_processes) as pool:
            test_results = pool.starmap(execute_t3sim_test, [(test, t3sim_args) for test in tests_to_execute])

def write_status_to_csv(rtl_args, t3sim_args):
    import status

    csv_name = f"status_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv"
    summary_csv_name = f"summary_{csv_name}"
    print("+ status will be written to:", csv_name)
    print("+ status will be written to:", summary_csv_name)

    status_args = dict()
    status_args["root_dir"]              = os.path.dirname(os.path.abspath(__file__))
    status_args["debug_dir"]             = os.path.join(rtl_args["local_test_bench_dir"], rtl_args["debug_dir"])
    status_args["t3sim_dir"]             = t3sim_args["sim_dir"]
    status_args["sim_result_yml"]        = rtl_args["sim_result_yml"]
    status_args["flatten_dict"]          = False # do not change this.
    status_args["test_dir_suffix"]       = rtl_args["test_dir_suffix"]
    status_args["rtl_log_file_suffix"]   = rtl_args["rtl_log_file_suffix"]
    status_args["t3sim_log_file_suffix"] = t3sim_args["t3sim_log_file_suffix"]
    status_args["assembly_yaml"]         = os.path.join(t3sim_args["sim_dir"], t3sim_args["binutils_dir"], "instruction_sets", t3sim_args["tensix_instructions_kind"], t3sim_args["assembly_yaml"]) # todo: automated instruction sets

    status.write_status_to_csv(status.get_status(tests, status_args), csv_name)
    status.write_regression(summary_csv_name)
    status.write_failure_types(summary_csv_name)
    status.write_s_curve(summary_csv_name)

if "__main__" == __name__:

    rtl_args = dict()
    rtl_args["debug_dir"]              = "rsim/debug" # todo: divide between path and debug dir name
    rtl_args["force"]                  = False
    rtl_args["git"]                    = "git@yyz-tensix-gitlab:tensix-hw/ws-tensix.git"
    rtl_args["hostname"]               = "auslogo2"
    rtl_args["infra_dir"]              = "infra"
    rtl_args["instructions_dir_path"]  = "src/meta"
    rtl_args["instructions_dir"]       = "instructions"
    rtl_args["num_processes"]          = 8
    rtl_args["project_yml"]            = "project.yml"
    rtl_args["sim_result_yml"]         = "sim_result.yml"
    rtl_args["suites"]                 = ""
    rtl_args["tags"]                   = ""
    rtl_args["test_bench_dir_path"]    = "/proj_tensix/user_dev/sjaju/work/may/15"
    rtl_args["test_bench_dir"]         = "ws-tensix"
    rtl_args["test_dir_suffix"]        =  "_0"
    rtl_args["tests_dir"]              =  "infra/tensix/rsim/tests"
    rtl_args["tests"]                  = None
    rtl_args["username"]               = getpass.getuser()
    # rtl_args["yml_files"]              = ["ttx-llk-sfpu.yml", "ttx-llk-fixed.yml"] if "/proj_tensix/user_dev/sjaju/work/apr/24" == rtl_args["test_bench_dir_path"] else ["ttx-test-llk-sfpu.yml", "ttx-test-llk.yml"]
    rtl_args["yml_files"]              = [
        # "cctb-l1-basic.yml",
        # "cctb-pack-basic.yml",
        # "cctb-srcs-basic.yml",
        "cctb-math-basic.yml",
        "cctb-sfpu-basic.yml",
        # "cctb-upk-basic.yml"
        ]
    rtl_args["local_test_bench_dir"]   = f"from-{rtl_args['test_bench_dir']}"
    rtl_args["rtl_log_file_suffix"]    = ".rtl_test.log"
    rtl_args["src_hd_proj_dir"]        = "proj"
    rtl_args["src_hd_proj_dir_path"]   = "src/hardware/tensix"
    rtl_args["src_firmware_dir"]       = "firmware"
    rtl_args["src_firmware_dir_path"]  = "src"

    t3sim_args = dict()
    t3sim_args["assembly_yaml"]                = "assembly.yaml"
    t3sim_args["binutils_git"]                 = "git@github.com:jajuTT/binutils-playground.git"
    t3sim_args["branch"]                       = "main" # t3sim branch
    t3sim_args["delay"]                        = 10
    t3sim_args["elf_files_dir"]                = rtl_args["debug_dir"].split("/")[-1] # "debug"
    t3sim_args["enable_sync"]                  = 1
    t3sim_args["force"]                        = False
    t3sim_args["git"]                          = "git@github.com:vmgeorgeTT/t3sim.git"
    t3sim_args["json_log_prefix"]              = "simreport_"
    t3sim_args["json_log_suffix"]              = ".json"
    t3sim_args["logs_dir"]                     = "logs"
    t3sim_args["max_num_threads_per_neo_core"] = 4
    # t3sim_args["mop_base_addr_str"]            = "0x80d000"
    t3sim_args["num_processes"]                = 8
    t3sim_args["sim_dir"]                      = "t3sim"
    t3sim_args["start_function"]               = "main"
    t3sim_args["tensix_instructions_kind"]     = "ttqs" # todo: automatic.
    t3sim_args["test_dir_suffix"]              = rtl_args["test_dir_suffix"] # "_0"
    t3sim_args["debug_dir"]                    = os.path.join(rtl_args["local_test_bench_dir"], rtl_args["debug_dir"])
    t3sim_args["cfg_dir"]                      = "cfg"
    t3sim_args["t3sim_log_file_suffix"]        = ".t3sim_test.log"

    # setup_rtl_environment(hostname, remote_dir_path)

    print(f"+ Remote server: {rtl_args["hostname"]}")
    print(f"+ Remote RTL test bench directory: {os.path.join(rtl_args["test_bench_dir_path"], rtl_args["test_bench_dir"])}")

    # tests = get_test_names_from_rtl_test_bench(rtl_args)
    # print(f"+ Found {len(tests)} matching test(s) tests for the given tags, suites, and yml files.")
    # tests = [test for test in tests if test != "l1-quas-wr-rd-partial-grinder"]
    # print("- Number of tests to execute: ", len(tests))
    # print(f"+ We keep the tests only with 1 neo core.")
    # n1_tests = sorted([test for test in tests if "n1" in test])
    # other_tests = sorted([test for test in tests if test not in n1_tests])
    # if other_tests:
    #     print(f"+ Following {len(other_tests)} tests will not be considered:")
    #     for test in other_tests:
    #         print(f"  + {test}")

    # if n1_tests:
    #     print(f"+ If not executed already, the following {len(n1_tests)} will be executed on both RTL and via performance model:")
    #     for test in n1_tests:
    #         print(f"  + {test}")
    # else:
    #     msg  = f"- error: could not fine tests with single neo core.\n"
    #     msg += f"- {len(tests)} matching tests were found with the constraints set by tags, suites, and yml files.\n"
    #     for test in tests:
    #         msg += f"{test}\n"

    #     raise Exception(msg.rstrip())

    # tests = n1_tests
    # del n1_tests
    # del other_tests

    # yml_test_files = ["cctb-l1-basic.yml",
    #     "cctb-pack-basic.yml",
    #     "cctb-srcs-basic.yml",
    #     "cctb-math-basic.yml",
    #     "cctb-sfpu-basic.yml",
    #     "cctb-upk-basic.yml"]

    # for each yml file, get list of tests, and run the tests.

    # for yml_file in yml_test_files:
    #     rtl_args["yml_files"] = [yml_file]
    #     rtl_args["tests"] = get_
    #     tests = get_all_tests(rtl_args)

    tests = get_all_tests_from_yml_files(rtl_args)
    print(f"+ Found {len(tests)} from {len(rtl_args["yml_files"])} yml test files")
    print(f"  + YML files: ")
    for ele in rtl_args["yml_files"]:
        print(f"    + {ele}")
    print("  + Tests: ")
    for idx, ele in enumerate(tests):
        print(f"    + {idx}. {ele}")

    execute_rtl_tests(tests, rtl_args)

    # execute_t3sim_tests(tests, t3sim_args, rtl_args)

    # write_status_to_csv(rtl_args, t3sim_args)



# todo:
# 1. move rtl_test.log to respective test directories.
# 2. no hardcoded names. sys.path.append("t3sim/binutils-playground")
# 3. no debug_prev. overwrite debug.
# 4. ..