#!/usr/bin/env python

import os
import sys
sys.path.append("polaris_big")
sys.path.append("polaris_big/ttsim/front/llk")

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
import paramiko
import paramiko.ssh_exception
import pathlib
import re
import read_elf
import rtl_utils
import shlex
import shutil
import subprocess
import sys
import t3sim_utils
import tensix
import yaml

class polaris_big_tests:
    @staticmethod
    def check_and_update_isa_file(rtl_args, model_args):
        # key_model_instruction_kind = "instruction_kind"
        # key_model_instruction_sets_dir = "pb_instruction_sets_dir"
        # key_model_root_dir = "pb_root_dir"
        # key_model_root_dir_path = "pb_root_dir_path"
        # key_rtl_isa_file_name = f"isa_file_name"
        # key_rtl_local_root_dir = "local_root_dir"
        # key_rtl_local_root_dir_path = "local_root_dir_path"

        # for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
        #     assert key in rtl_args.keys(), f"- error: {key} not found in given args dict"

        # for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_t3sim_")]:
        #     assert key in model_args.keys(), f"- error: {key} not found in given args dict"

        # rtl_utils.rtl_tests.copy_partial_src(rtl_args)

        # rtl_root_dir_incl_path = os.path.join(rtl_args[key_rtl_local_root_dir_path], rtl_args[key_rtl_local_root_dir])
        # rtl_isa_file_name_incl_path = rtl_utils.test_names.get_file_name_incl_path(rtl_root_dir_incl_path, rtl_args[key_rtl_isa_file_name])
        # if not os.path.isfile(rtl_isa_file_name_incl_path):
        #     raise Exception(f"- error: could not find file {rtl_isa_file_name_incl_path}")

        # polaris_big_dir_incl_path = os.path.join(model_args[key_model_root_dir_path], model_args[key_model_root_dir])
        # polaris_big_isa_file_incl_path = [ele for ele in rtl_utils.test_names.get_file_names_incl_path(polaris_big_dir_incl_path, rtl_args[key_rtl_isa_file_name]) if os.path.join(model_args[key_model_instruction_kind], rtl_args[key_rtl_isa_file_name]) in ele]
        # print("- polaris_big_dir_incl_path: ", polaris_big_dir_incl_path)
        # print("- polaris_big_isa_file_incl_path: ", polaris_big_isa_file_incl_path)
        # print()

        # if 0 == len(polaris_big_isa_file_incl_path): # file doesn't exist.
        #     instruction_sets_dir_incl_path = rtl_utils.test_names.get_dir_incl_path(polaris_big_dir_incl_path, model_args[key_model_instruction_sets_dir])
        #     polaris_big_isa_dir_incl_path = os.path.join(instruction_sets_dir_incl_path, model_args[key_model_instruction_kind])
        #     os.makedirs(polaris_big_isa_dir_incl_path, exist_ok = True)
        #     shutil.copy(rtl_isa_file_name_incl_path, polaris_big_isa_dir_incl_path)

        # elif 1 == len(polaris_big_isa_file_incl_path):
        #     polaris_big_isa_file_incl_path = polaris_big_isa_file_incl_path[0]
        #     if not os.path.isfile(rtl_isa_file_name_incl_path):
        #         raise Exception(f"- error: could not find file {rtl_isa_file_name_incl_path}")

        #     filecmp.clear_cache()
        #     if not filecmp.cmp(rtl_isa_file_name_incl_path, polaris_big_isa_file_incl_path):
        #         t3sim_utils.rename_with_timestamp(polaris_big_isa_file_incl_path)

        #     shutil.copy(rtl_isa_file_name_incl_path, str(pathlib.Path(polaris_big_isa_file_incl_path).parent))

        # else:
        #     raise Exception(f"- error: found multiple isa files. binutils_isa_file_incl_path: {polaris_big_isa_file_incl_path}")

    # @staticmethod
    # def clone_polaris_big_and_update_assembly_yaml_if_required(rtl_args, t3sim_args, model_args):
        def clone_polaris_big_if_required(args):
            key_model_force = "force"
            key_model_git_branch = "model_git_branch"
            key_model_git_url = "model_git_url"
            key_model_root_dir = "model_root_dir"

            for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
                assert key in args.keys(), f"- error: {key} not found in given args dict"

            model_root_dir = args[key_model_root_dir]

            if args[key_model_force] or (not os.path.isdir(model_root_dir)):
                if os.path.isdir(model_root_dir):
                    shutil.rmtree(model_root_dir)

                cmd = f"git clone {args[key_model_git_url]} && cd {model_root_dir} && git checkout {args[key_model_git_branch]} && cd .."

                result = subprocess.run(
                    cmd,
                    shell = True,
                    capture_output = True,       # collect stdout / stderr
                    check = True,                # raise CalledProcessError if exit-code ≠ 0
                    timeout = 3600,              # optional: abort after N seconds
                    )

            if not os.path.isdir(model_root_dir):
                raise Exception(f"- error: could not find directory {model_root_dir}")

        def update_assembly_yaml_if_required(rtl_args, model_args):
            key_model_instruction_kind = "instruction_kind"
            key_model_instruction_sets_dir = "model_instruction_sets_dir"
            key_model_root_dir = "model_root_dir"
            key_model_root_dir_path = "model_root_dir_path"
            key_rtl_isa_file_name = f"isa_file_name"
            key_rtl_local_root_dir = "local_root_dir"
            key_rtl_local_root_dir_path = "local_root_dir_path"

            for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
                assert key in rtl_args.keys(), f"- error: {key} not found in given rtl args dict"

            for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_model_")]:
                assert key in model_args.keys(), f"- error: {key} not found in given model args dict"

            rtl_root_dir_incl_path = os.path.join(rtl_args[key_rtl_local_root_dir_path], rtl_args[key_rtl_local_root_dir])
            rtl_isa_file_name_incl_path = rtl_utils.test_names.get_file_name_incl_path(rtl_root_dir_incl_path, rtl_args[key_rtl_isa_file_name])
            if not os.path.isfile(rtl_isa_file_name_incl_path):
                raise Exception(f"- error: could not find file {rtl_isa_file_name_incl_path}")

            polaris_big_dir_incl_path = os.path.join(model_args[key_model_root_dir_path], model_args[key_model_root_dir])
            polaris_big_isa_file_incl_path = [ele for ele in rtl_utils.test_names.get_file_names_incl_path(polaris_big_dir_incl_path, rtl_args[key_rtl_isa_file_name]) if os.path.join(model_args[key_model_instruction_kind], rtl_args[key_rtl_isa_file_name]) in ele]
            print("polaris_big_dir_incl_path: ", polaris_big_dir_incl_path)
            print("polaris_big_isa_file_incl_path: ", polaris_big_isa_file_incl_path)

            if 0 == len(polaris_big_isa_file_incl_path): # file doesn't exist.
                instruction_sets_dir_incl_path = rtl_utils.test_names.get_dir_incl_path(polaris_big_dir_incl_path, model_args[key_model_instruction_sets_dir])
                polaris_big_isa_dir_incl_path = os.path.join(instruction_sets_dir_incl_path, model_args[key_model_instruction_kind])
                os.makedirs(polaris_big_isa_dir_incl_path, exist_ok = True)
                shutil.copy(rtl_isa_file_name_incl_path, polaris_big_isa_dir_incl_path)

            elif 1 == len(polaris_big_isa_file_incl_path):
                polaris_big_isa_file_incl_path = polaris_big_isa_file_incl_path[0]
                if not os.path.isfile(rtl_isa_file_name_incl_path):
                    raise Exception(f"- error: could not find file {rtl_isa_file_name_incl_path}")

                filecmp.clear_cache()
                if not filecmp.cmp(rtl_isa_file_name_incl_path, polaris_big_isa_file_incl_path):
                    t3sim_utils.rename_with_timestamp(polaris_big_isa_file_incl_path)

                shutil.copy(rtl_isa_file_name_incl_path, str(pathlib.Path(polaris_big_isa_file_incl_path).parent))

            else:
                raise Exception(f"- error: found multiple isa files. binutils_isa_file_incl_path: {polaris_big_isa_file_incl_path}")

        clone_polaris_big_if_required(model_args)
        rtl_utils.rtl_tests.copy_partial_src(rtl_args)
        update_assembly_yaml_if_required(rtl_args, model_args)

    @staticmethod
    def write_cfg_file(test_id, test, rtl_args, model_args):
        key_model_cfg_dir         = "model_cfg_dir"
        key_model_cfg_file_prefix = "model_cfg_file_prefix"
        key_model_root_dir        = "model_root_dir"
        key_model_root_dir_path   = "model_root_dir_path"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
            assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_model_")]:
            assert key in model_args.keys(), f"- error: {key} not found in given model_args dict"

        cfg_dict = t3sim_utils.t3sim_tests.get_cfg(test_id, test, rtl_args, model_args)
        cfg_dir_incl_path = os.path.join(model_args[key_model_root_dir_path], model_args[key_model_root_dir], model_args[key_model_cfg_dir])
        if not os.path.isdir(cfg_dir_incl_path):
            os.makedirs(cfg_dir_incl_path, exist_ok = True)

        file_name = os.path.join(cfg_dir_incl_path, f"{model_args[key_model_cfg_file_prefix]}{test}.json")
        with open(file_name, 'w') as file:
            json.dump(cfg_dict, file, indent = 2)

        return file_name

    @staticmethod
    def get_inputcfg(test_id, test, rtl_args, model_args):
        key_model_start_function    = "start_function"
        key_rtl_local_root_dir      = "local_root_dir"
        key_rtl_local_root_dir_path = "local_root_dir_path"
        key_rtl_test_dir_suffix     = "test_dir_suffix"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
            assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_t3sim_")]:
            assert key in model_args.keys(), f"- error: {key} not found in given rtl_args dict"

        local_root_dir_incl_path = os.path.join(rtl_args[key_rtl_local_root_dir_path], rtl_args[key_rtl_local_root_dir])
        test_dir = test + rtl_args[key_rtl_test_dir_suffix]
        for pwd, _, _ in os.walk(local_root_dir_incl_path):
            if pwd.endswith(test_dir):
                test_dir_incl_path = pwd

        if "test_dir_incl_path" not in locals():
            raise Exception(f"- error: test_dir_incl_path not set, most likely did not find {test_dir} in path {local_root_dir_incl_path}")

        input_cfg_dict                = dict()
        input_cfg_dict["description"] = dict()
        input_cfg_dict["input"]       = dict()
        input_cfg                     = input_cfg_dict["input"]
        input_cfg["syn"]              = 0
        input_cfg["name"]             = test
        num_neos                      = t3sim_utils.get_num_neos(test_dir_incl_path)

        for neo_id in range(num_neos):
            tc_key = f"tc{neo_id}"
            input_neo = dict()
            neo_dir = f"neo_{neo_id}"
            for pwd, _, _ in os.walk(test_dir_incl_path):
                if pwd.endswith(neo_dir):
                    num_threads = t3sim_utils.get_num_threads(pwd)
                    if num_threads in {0, None}:
                        raise Exception(f"- error: expected at least one thread, received {num_threads}. Path: {pwd}")

                    input_neo["startFunction"] = model_args[key_model_start_function]
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

        return input_cfg_dict

    @staticmethod
    def write_inputcfg_file(test_id, test, rtl_args, model_args):
        key_root_dir        = "model_root_dir"
        key_cfg_dir         = "model_cfg_dir"
        key_inputcfg_prefix = "model_inputcfg_file_prefix"
        key_root_dir_path   = "model_root_dir_path"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
            assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_model_")]:
            assert key in model_args.keys(), f"- error: {key} not found in given rtl_args dict"

        input_cfg_dict = polaris_big_tests.get_inputcfg(test_id, test, rtl_args, model_args)

        cfg_dir_incl_path = os.path.join(model_args[key_root_dir_path], model_args[key_root_dir], model_args[key_cfg_dir])
        if not os.path.isdir(cfg_dir_incl_path):
            os.makedirs(cfg_dir_incl_path, exist_ok = True)

        file_name = os.path.join(cfg_dir_incl_path, f"{model_args[key_inputcfg_prefix]}{test}.json")
        with open(file_name, 'w') as file:
            json.dump(input_cfg_dict, file, indent = 2)

        return file_name

    @staticmethod
    def execute_test(test_id, test, rtl_args, model_args):
        key_model_log_file_suffix = "model_log_file_suffix"
        key_model_odir = "model_odir"
        key_model_root_dir = "model_root_dir"
        key_model_root_dir_path = "model_root_dir_path"
        key_model_simreport = "model_simreport"
        key_model_log_file_end = "model_log_file_end"
        key_model_force = "force"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_model_")]:
            assert key in model_args.keys(), f"- error: {key} not found in given rtl_args dict"

        inputcfg_file_name = polaris_big_tests.write_inputcfg_file(test_id, test, rtl_args, model_args)
        cfg_file_name = polaris_big_tests.write_cfg_file(test_id, test, rtl_args, model_args)

        pb_dir_incl_path = os.path.join(model_args[key_model_root_dir_path], model_args[key_model_root_dir])
        odir_incl_path = os.path.join(pb_dir_incl_path, model_args[key_model_odir])
        log_file_name = os.path.join(odir_incl_path, f"{test}{model_args[key_model_log_file_suffix]}")

        if not os.path.isdir(odir_incl_path):
            os.makedirs(odir_incl_path, exist_ok = True)

        if not model_args[key_model_force]:
            skip_test = True
            if os.path.isfile(log_file_name):
                with open(log_file_name) as file:
                    lines = file.readlines()
                    if not lines[-1].strip().startswith(model_args[key_model_log_file_end]):
                        skip_test = False

            if skip_test:
                for pwd, _, files in os.walk(odir_incl_path):
                    for file in files:
                        if file.startswith(model_args[key_model_simreport]) and (test in file):
                            return

        cmds = [
            f"cd {pb_dir_incl_path}",
            f"PYTHONPATH='.' python ttsim/back/tensix_neo/tneoSim.py --cfg {cfg_file_name} --inputcfg {inputcfg_file_name} --odir {model_args[key_model_odir]}"
        ]
        cmd = " && ".join(cmds)
        print(f"- test ID: {test_id}, executing: {cmd}")

        with open(log_file_name, "w") as log_file:
            subprocess.call(
            cmd,
            shell=True,
            stdout=log_file,
            stderr=subprocess.STDOUT)

    @staticmethod
    def execute_tests(tests, rtl_args, model_args):
        assert isinstance(rtl_args, dict), "- error: expected rtl_args to be a dict"
        assert isinstance(model_args, dict), "- error: expected model_args to be a dict"

        key_num_processes = "num_processes"
        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in rtl_args.keys(), f"- error: {key} not found in given args dict"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in model_args.keys(), f"- error: {key} not found in given args dict"

        polaris_big_tests.check_and_update_isa_file(rtl_args, model_args)

        num_processes = min([rtl_args[key_num_processes], model_args[key_num_processes], len(tests)])
        print(f"- Number of t3sim tests to execute:                          {len(tests)}")
        print(f"- Number of parallel processes to execute polaris_big tests: {num_processes}")

        with multiprocessing.Pool(processes = num_processes) as pool:
            test_results = pool.starmap(polaris_big_tests.execute_test, [(idx, test, rtl_args, model_args) for idx, test in enumerate(sorted(tests))])