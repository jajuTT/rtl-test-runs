#!/usr/bin/env python

import collections
import contextlib
import datetime
import datetime
import fabric
import filecmp
import functools
import getpass
import itertools
import json
import multiprocessing
import os
import paramiko
import paramiko.ssh_exception
import pathlib
import rtl_utils
import shlex
import shutil
import subprocess
import sys
import yaml

def rename_with_timestamp(path: str | pathlib.Path,
    *,
    format: str = "%Y%m%d_%H%M%S",   # 20231130_234501
    time_zone  = datetime.timezone.utc) -> pathlib.Path:
    # Rename *path* to "<stem>_<timestamp><suffix>" and return the new Path.
    # logfile.txt  ->  logfile_20231130_234501.txt

    p  = pathlib.Path(path)
    ts = datetime.datetime.now(time_zone).strftime(format)     # one shot: consistent everywhere
    new_name = f"{p.stem}_{ts}{p.suffix}"
    new_path = p.with_name(new_name)
    p.rename(new_path)
    return new_path

def get_num_dirs_with_keyword(path, keyword):
    for _, sub_dirs, _ in os.walk(path):
        if any(sub_dir.startswith(keyword) for sub_dir in sub_dirs):
            kw_dirs = []
            for sub_dir in sub_dirs:
                if sub_dir.startswith(keyword):
                    kw_dirs.append(sub_dir)

            kw_dirs = sorted(kw_dirs)
            if not kw_dirs:
                raise Exception(f"- error: did not find any directories with keyword {keyword} in path {path}")

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

class t3sim_tests:
    @staticmethod
    def clone_t3sim_and_update_assembly_yaml_if_required(rtl_args, t3sim_args):
        def clone_t3sim_if_required(args):
            key_force = "force"
            key_t3sim_git_branch = "t3sim_git_branch"
            key_t3sim_git_url = "t3sim_git_url"
            key_t3sim_root_dir = "t3sim_root_dir"

            for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
                assert key in args.keys(), f"- error: {key} not found in given args dict"

            t3sim_root_dir = args[key_t3sim_root_dir]

            if args[key_force] or (not os.path.isdir(t3sim_root_dir)):
                if os.path.isdir(t3sim_root_dir):
                    shutil.rmtree(t3sim_root_dir)

                cmd = f"git clone {args[key_t3sim_git_url]} && cd {t3sim_root_dir} && git checkout {args[key_t3sim_git_branch]} && cd .."

                result = subprocess.run(
                    cmd,
                    shell = True,
                    capture_output = True,       # collect stdout / stderr
                    check = True,                # raise CalledProcessError if exit-code ≠ 0
                    timeout = 3600,              # optional: abort after N seconds
                    )

            if not os.path.isdir(t3sim_root_dir):
                raise Exception(f"- error: could not find directory {t3sim_root_dir}")

        def clone_binutils_if_required(args):
            key_force = "force"
            key_t3sim_root_dir = "t3sim_root_dir"
            key_binutils_git_url = "binutils_git_url"
            key_binutils_root_dir = "binutils_root_dir"

            for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
                assert key in args.keys(), f"- error: {key} not found in given args dict"

            t3sim_root_dir = args[key_t3sim_root_dir]
            binutils_root_dir = args[key_binutils_root_dir]

            binutils_dir_incl_path = os.path.join(t3sim_root_dir, binutils_root_dir)

            if args[key_force] or (not os.path.isdir(binutils_root_dir)):
                if os.path.isdir(binutils_root_dir):
                    shutil.rmtree(binutils_root_dir)

                cmds = f"cd {shlex.quote(t3sim_root_dir)} && git clone {shlex.quote(args[key_binutils_git_url])} && cd -"

                result = subprocess.run(
                    cmds,
                    shell = True,
                    capture_output = True,       # collect stdout / stderr
                    check = True,                # raise CalledProcessError if exit-code ≠ 0
                    timeout = 3600,              # optional: abort after N seconds
                    )

            if not os.path.isdir(binutils_dir_incl_path):
                raise Exception(f"- error: could not find directory {binutils_dir_incl_path}")

        def update_assembly_yaml_if_required(rtl_args, t3sim_args):
            key_rtl_isa_file_name = f"isa_file_name"
            key_rtl_src_dir = "src_dir"
            key_rtl_local_root_dir = "local_root_dir"
            key_rtl_local_root_dir_path = "local_root_dir_path"
            key_t3sim_t3sim_root_dir = "t3sim_root_dir"
            key_t3sim_binutils_root_dir = "binutils_root_dir"
            key_t3sim_instruction_kind = "instruction_kind"

            for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
                assert key in rtl_args.keys(), f"- error: {key} not found in given args dict"

            for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_t3sim_")]:
                assert key in t3sim_args.keys(), f"- error: {key} not found in given args dict"

            src_dir_incl_path = os.path.join(rtl_args[key_rtl_local_root_dir_path], rtl_args[key_rtl_local_root_dir], rtl_args[key_rtl_src_dir])
            rtl_isa_file_name_incl_path = rtl_utils.test_names.get_file_name_incl_path(src_dir_incl_path, rtl_args[key_rtl_isa_file_name])
            if not os.path.isfile(rtl_isa_file_name_incl_path):
                raise Exception(f"- error: could not find file {rtl_isa_file_name_incl_path}")

            binutils_dir_incl_path = os.path.join(t3sim_args[key_t3sim_t3sim_root_dir], t3sim_args[key_t3sim_binutils_root_dir])
            binutils_isa_file_incl_path = [ele for ele in rtl_utils.test_names.get_file_names_incl_path(binutils_dir_incl_path, rtl_args[key_rtl_isa_file_name]) if os.path.join(t3sim_args[key_t3sim_instruction_kind], rtl_args[key_rtl_isa_file_name]) in ele]

            if 0 == len(binutils_dir_incl_path): # file doesn't exist.
                binutils_isa_dir_incl_path = os.path.join(binutils_dir_incl_path, "instruction_sets", t3sim_args[key_t3sim_instruction_kind])
                os.makedirs(binutils_isa_dir_incl_path, exist_ok = True)
                shutil.copy(rtl_isa_file_name_incl_path, binutils_isa_dir_incl_path)

            elif 1 == len(binutils_isa_file_incl_path):
                binutils_isa_file_incl_path = binutils_isa_file_incl_path[0]
                if not os.path.isfile(rtl_isa_file_name_incl_path):
                    raise Exception(f"- error: could not find file {rtl_isa_file_name_incl_path}")

                filecmp.clear_cache()
                if not filecmp.cmp(rtl_isa_file_name_incl_path, binutils_isa_file_incl_path):
                    rename_with_timestamp(binutils_isa_file_incl_path)

                shutil.copy(rtl_isa_file_name_incl_path, str(pathlib.Path(binutils_isa_file_incl_path).parent))

            else:
                raise Exception(f"- error: found multiple isa files. binutils_isa_file_incl_path: {binutils_isa_file_incl_path}")

        clone_t3sim_if_required(t3sim_args)
        clone_binutils_if_required(t3sim_args)
        rtl_utils.rtl_tests.copy_partial_src(rtl_args)
        update_assembly_yaml_if_required(rtl_args, t3sim_args)

    @staticmethod
    def write_cfg_file(test_id, test, args):
        pass

    @staticmethod
    def write_inputcfg_file(test_id, test, rtl_args, t3sim_args):
        key_rtl_local_root_dir_path     = "local_root_dir_path"
        key_rtl_local_root_dir          = "local_root_dir"
        key_rtl_test_dir_suffix         = "test_dir_suffix"
        key_t3sim_start_function        = "start_function"
        key_t3sim_t3sim_root_dir        = "t3sim_root_dir"
        key_t3sim_t3sim_cfg_dir         = "t3sim_cfg_dir"
        key_t3sim_t3sim_inputcfg_prefix = "t3sim_inputcfg_prefix"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
            assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_t3sim_")]:
            assert key in t3sim_args.keys(), f"- error: {key} not found in given rtl_args dict"

        local_root_dir_incl_path = os.path.join(rtl_args[key_rtl_local_root_dir_path], rtl_args[key_rtl_local_root_dir])
        test_dir = test + rtl_args[key_rtl_test_dir_suffix]
        for pwd, _, _ in os.walk(local_root_dir_incl_path):
            if pwd.endswith(test_dir):
                test_dir_incl_path = pwd

        if "test_dir_incl_path" not in locals():
            raise Exception(f"- error: test_dir_incl_path not set, most likely did not find {test_dir} in path {local_root_dir_incl_path}")
        
        input_cfg_dict                = dict()
        input_cfg_dict["syn"]         = 0
        input_cfg_dict["name"]        = test
        input_cfg_dict["description"] = dict()
        input_cfg_dict["input"]       = dict()
        input_cfg                     = input_cfg_dict["input"]
        num_neos                      = get_num_neos(test_dir_incl_path)

        for neo_id in range(num_neos):
            tc_key = f"tc{neo_id}"            
            input_neo = dict()
            neo_dir = f"neo_{neo_id}"
            for pwd, _, _ in os.walk(test_dir_incl_path):
                if pwd.endswith(neo_dir):
                    num_threads = get_num_threads(pwd)
                    if num_threads in {0, None}:
                        raise Exception(f"- error: expected at least one thread, received {num_threads}. Path: {pwd}")

                    input_neo["startFunction"] = t3sim_args[key_t3sim_start_function]
                    input_neo["numThreads"] = num_threads

                    neo_os_walk = os.walk(pwd)
                    for pwd1, _, files in neo_os_walk:
                        for file in files:
                            if file.endswith(".elf"):
                                thread_id = int(file.split("_")[-1].split(".")[0])
                                if thread_id > num_threads:
                                    raise Exception(f"- error: thread id is greater than number of threads. thread_id: {thread_id}, number of threads: {num_threads}")
                                input_neo[f"th{thread_id}Path"] = pwd1
                                input_neo[f"th{thread_id}Elf"] = file

            input_cfg[tc_key] = {key : input_neo[key] for key in sorted(input_neo.keys())}
        
        if "dvalid" in test:
            msg = f"{test} contains dvalid.\n"
            msg += "in the inputcfg we are going to make the following changes.\n"
            msg += "1. check that it has 3 threads, change it to 4 threads\n"
            msg += "1. move thread 2 path and files to thread 3\n"
            msg += "1. leave thread 2 empty\n"

            print(msg)

            for neo_id in range(num_neos):
                tc_key = f"tc{neo_id}"

                if 3 != input_cfg[tc_key]["numThreads"]:
                    raise Exception(f"- error: expected numThreads to be 3, received {input_cfg[tc_key]["numThreads"]}. Core: {tc_key}")

                input_cfg[tc_key]["numThreads"] = 4 # change it to 4.

                # add thread 3
                input_cfg[tc_key]["th3Path"] = input_cfg[tc_key]["th2Path"]
                input_cfg[tc_key]["th3Elf"]  = input_cfg[tc_key]["th2Elf"]

                # make thread 2 empty
                input_cfg[tc_key][f"th2Path"] = ""
                input_cfg[tc_key][f"th2Elf"]  = ""

        cfg_dir_incl_path = os.path.join(t3sim_args[key_t3sim_t3sim_root_dir], t3sim_args[key_t3sim_t3sim_cfg_dir])
        if not os.path.isdir(cfg_dir_incl_path):
            os.makedirs(cfg_dir_incl_path, exist_ok = True)

        file_name = os.path.join(cfg_dir_incl_path, f"{t3sim_args[key_t3sim_t3sim_inputcfg_prefix]}{test}.json")
        with open(file_name, 'w') as file:
            json.dump(input_cfg_dict, file, indent = 2)

        return input_cfg_dict

    @staticmethod
    def execute_test(test_id, test, rtl_args, t3sim_args):
        t3sim_tests.write_inputcfg_file(test_id, test, rtl_args, t3sim_args)
        # t3sim_tests.write_cfg_dir(test_id, test, args)

    @staticmethod
    def execute_tests(tests, rtl_args, t3sim_args):
        assert isinstance(rtl_args, dict), "- error: expected rtl_args to be a dict"
        assert isinstance(t3sim_args, dict), "- error: expected t3sim_args to be a dict"
        key_num_processes = "num_processes"
        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in rtl_args.keys(), f"- error: {key} not found in given args dict"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in t3sim_args.keys(), f"- error: {key} not found in given args dict"

        num_processes = min([rtl_args[key_num_processes], t3sim_args[key_num_processes], len(tests)])
        print(f"- Number of RTL tests to execute:                    {len(tests)}")
        print(f"- Number of parallel processes to execute RTL tests: {num_processes}")
        
        with multiprocessing.Pool(processes = num_processes) as pool:
            test_results = pool.starmap(t3sim_tests.execute_test, [(idx, test, rtl_args, t3sim_args) for idx, test in enumerate(tests)])



        









