#!/usr/bin/env python

import collections
import datetime
import datetime
import fabric
import functools
import getpass
import itertools
import json
import math
import multiprocessing
import os
import paramiko
import rtl_utils
import shlex
import sys
import t3sim_utils

def reserve_tensix_ird_instance(username = None, hostname = "yyz-ird", machine = None, key = os.path.expanduser("~/.ssh/id_ed25519")):
    def get_ird_selection_id(msg):
        def str_to_table_dict(msg):
            import re
            lines = msg.strip().splitlines()

            if len(lines) < 2:
                raise Exception(f"- error: expected minimum 2 lines, received {len(lines)}, most likely the ird instance was not reserved. The method assumes at least one ird instance is allocated. given string: {msg}")
            rows = []
            # split header and data on runs of 2+ spaces

            cols = re.split(r'\s{2,}', lines[0].strip())
            data = [dict(zip(cols, re.split(r'\s{2,}', line.strip()))) for line in lines[1:]]

            print(data)

            return data

        table_dict = str_to_table_dict(msg)

        print(msg)
        selection_id = table_dict[-1]["SELECTION ID"]
        machine      = table_dict[-1]["MACHINE"]
        port         = table_dict[-1]["SSH PORT"]

        print(f"- selection ID: {selection_id}")

        return selection_id, machine, port
        # TODO: check timestamp. For now, the assumption is ird instance is reserved and we are returning the latest one.

    hostname = "yyz-ird"
    if not username:
        username = getpass.getuser()

    with fabric.Connection(
        hostname, 
        user = username, 
        connect_kwargs = {"key_filename": key}) as conn:
        cmd = f'ird reserve --cluster=tt_aus --team=tensix_interactive --timeout="max" --docker-image=centos7 compute'
        if machine:
            cmd += f' --machine={machine}'

        print(f"- executing command {cmd} on remote server {hostname}")
        result = conn.run(cmd)
        if result.exited:
            msg  = f"- error: could not reserve a tensix IRD container.\n"
            msg += f"- command executed:   {cmd}\n"
            msg += f"- exit staus:         {result.exited}\n"
            msg += f"- messages to stdout: {result.stdout}\n"
            msg += f"- messages to stderr: {result.stderr}"
            raise Exception(msg)

        cmd = f'ird list'
        print(f"- executing command {cmd} on remote server {hostname}")
        result = conn.run(cmd, hide=True, warn=True)
        if result.exited:
            msg  = f"- error: could not execute {cmd} on server {hostname}.\n"
            msg += f"- command executed:   {cmd}\n"
            msg += f"- exit staus:         {result.exited}\n"
            msg += f"- messages to stdout: {result.stdout}\n"
            msg += f"- messages to stderr: {result.stderr}"
            raise Exception(msg)
        
        selection_id, hostname, port = get_ird_selection_id(result.stdout)

        conn = rtl_utils.copy.safe_connection(
            host = hostname, 
            user = username, 
            port = port, 
            connect_kwargs={"key_filename": key})

        return (selection_id, hostname, port)

def ird_release(selection_id, username = None):
    hostname = "yyz-ird"
    if not username:
        username = getpass.getuser()

    with fabric.Connection(hostname, user = username) as conn:
        cmd = f"ird release {selection_id}"
        print(f"- executing {cmd} on remote server {hostname}")
        conn.run(cmd)

def clone_rtl_test_bench_at(path, repo_dir, machine, port, username = None):
    repo_url  = f"git@yyz-tensix-gitlab:tensix-hw/{repo_dir}.git"
    if not username:
        username = getpass.getuser()

    with fabric.Connection(
        host = machine,
        user = username,
        port = port) as conn:

        cmd = f"mkdir -p {path}"
        print(f"- executing command {cmd} on server {machine}, port {port}")
        res = conn.run(cmd, hide = True)
        if res.exited:
            raise Exception(f"- could not create directory {path} on server {machine}, port {port}")

        with conn.cd(path):
            if not conn.run(f"test -d {repo_dir}", warn=True).failed:
                backup_dir = f"{repo_dir}_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                cmd = f"mv {repo_dir} {backup_dir}"
                print(f"- executing command {cmd} on server {machine}, port {port}")
                res = conn.run(cmd, hide = True)
                if res.exited:
                    raise Exception(f"- could not move directory {repo_dir} to {backup_dir} on server {machine}, port {port}")

            cmd = f"git clone {repo_url}"
            print(f"- executing command {cmd} on server {machine}, port {port}")
            res = conn.run(cmd, timeout = 7200)
            if res.exited:
                raise Exception(f"- could not create directory {path} on server {machine}, port {port}")

def clone_rtl_test_bench(repo_dir, machine, port, username = None):
    month_str =  datetime.datetime.now().strftime('%B').lower()
    day_str   = f"{datetime.datetime.now().day:02d}"
    path      = f"/proj_tensix/user_dev/sjaju/work/{month_str}/{day_str}"

    clone_rtl_test_bench_at(path, repo_dir, machine, port, username)

    return path

def build_rtl_test_bench(path, repo_dir, machine, port, username = None):
    repo_path = os.path.join(path, repo_dir)
    if not username:
        username = getpass.getuser()

    with fabric.Connection(
        host = machine,
        user = username,
        port = port) as conn:

        if conn.run(f"test -d {repo_path}", warn=True).failed:
            raise Exception(f"- error: could not find {repo_path} on remote server {machine}, port {port}")

        with conn.cd(repo_path):
            cmds = []
            # cmds.append("make submod-sync")
            # cmds.append("source .condasetup")
            # cmds.append("source SETUP.cctb.local.sh")
            # cmds.append("bender checkout")
            # cmds.append("cd $ROOT")
            # cmds.append("make")
            # cmds.append("make pc")
            # cmds.append("make -C src/verif/tensix/dpi")

            # cmd = ' && '.join(cmds)
            # print(f"- executing command {cmd} on server {machine}, port {port}")
            # conn.run(cmd, timeout = 7200)

            # cmds = []
            # cmds.append(f"pwd")
            # cmds.append(f"make submod-sync")
            # cmds.append(f"source .condasetup")
            # cmds.append(f"source SETUP.cctb.local.sh")
            # cmds.append(f"rsim run_test --test t6-quas-n1-ttx-elwadd-broadcast-col-fp16-llk")
            # cmd = ' && '.join(cmds)
            # print(f"- executing command {cmd} on server {machine}, port {port}")
            # conn.run(cmd, timeout = 1800)
            
            
            cmds.append("source SETUP.cctb.local.sh")
            cmds.append("make allclean")
            cmds.append("make all")

            cmd = ' && '.join(cmds)
            print(f"- executing command {cmd} on server {machine}, port {port}")
            conn.run(cmd, timeout = 7200)

            cmds = []
            cmds.append(f"pwd")
            cmds.append(f"source SETUP.cctb.local.sh")
            cmds.append(f"rsim run_test --test t6-quas-n1-ttx-elwadd-broadcast-col-fp16-llk")
            cmd = ' && '.join(cmds)
            print(f"- executing command {cmd} on server {machine}, port {port}")
            conn.run(cmd, timeout = 1800)

def execute_rtl_test_cases(tests, tags, suites, machine, port, username = None):
    force           = args["force"]               if "force"               in args.keys() else False
    hostname        = args["hostname"]            if "hostname"            in args.keys() else "auslogo2"
    infra_dir       = args["infra_dir"]           if "infra_dir"           in args.keys() else "infra"
    project_yml     = args["project_yml"]         if "project_yml"         in args.keys() else "project.yml"
    remote_dir      = args["test_bench_dir"]      if "test_bench_dir"      in args.keys() else "ws-tensix"
    remote_dir_path = args["test_bench_dir_path"] if "test_bench_dir_path" in args.keys() else ""
    suites          = args["suites"]              if "suites"              in args.keys() else ""
    tags            = args["tags"]                if "tags"                in args.keys() else None
    tests           = args["tests"]               if "tests"               in args.keys() else None
    tests_dir       = args["tests_dir"]           if "tests_dir"           in args.keys() else "infra/tensix/rsim/tests"
    username        = args["username"]            if "username"            in args.keys() else getpass.getuser()
    yml_files       = args["yml_files"]           if "yml_files"           in args.keys() else ["ttx-test-llk-sfpu.yml", "ttx-test-llk.yml"]
    local_rtl_dir   = args["local_ws-tensix_dir"] if "local_ws-tensix_dir" in args.keys() else f"from-{remote_dir}" # todo change this to appropriate key values.

def check_rtl_test_bench_path_clone_and_build_if_required(path, repo_dir, machine, port, username = None):
    if not username:
        username = getpass.getuser()

    with fabric.Connection(
        host = machine,
        user = username,
        port = port) as conn:

        cmd = f"mkdir -p {path}"
        print(f"- executing command {cmd} on server {machine}, port {port}")
        res = conn.run(cmd, hide = True)
        if res.exited:
            raise Exception(f"- error: could not create directory {path} on server {machine}, port {port}")

        with conn.cd(path):
            if conn.run(f"test -d {repo_dir}", warn=True).failed:
                clone_rtl_test_bench_at(path, repo_dir, machine, port, username)
            else:
                print(f"{repo_dir} exists at {path} on {machine}, port {port}")

            with conn.cd(repo_dir):
                cmd = r'''
                    bash -O nullglob -c '
                    files=(build*.log)
                    (( ${#files[@]} )) && echo FOUND || echo NONE
                    '
                    '''
                print(f"- executing command: {cmd} on {machine}, port {port}")
                res = conn.run(cmd)
                if res.stdout.strip() != "FOUND":
                    build_rtl_test_bench(path, repo_dir, machine, port, username)
                else:
                    print(f"rtl test bench already compiled and built")

if "__main__" == __name__:
    rtl_args = dict()

    rtl_args["suites"]    = "postcommit"
    rtl_args["tags"]      = None
    rtl_args["tests"]     = None
    # rtl_args["yaml_files"] = ["ttx-llk-sfpu.yml", "ttx-llk-fixed.yml"]
    rtl_args["yaml_files"] = {
        "ttx-llk-sfpu.yml"  : {"suites" : "postcommit"}, 
        "ttx-llk-fixed.yml" : {"suites" : "postcommit"}}
    # rtl_args["test_mode"] = "suites" # another acceptable option: all.

    # # rtl_args["yml_files"]              = ["ttx-llk-sfpu.yml", "ttx-llk-fixed.yml"] if "/proj_tensix/user_dev/sjaju/work/apr/24" == rtl_args["test_bench_dir_path"] else ["ttx-test-llk-sfpu.yml", "ttx-test-llk.yml"]
    # rtl_args["yml_files"]              = [
    #     # "cctb-l1-basic.yml",
    #     # "cctb-pack-basic.yml",
    #     # "cctb-srcs-basic.yml",
    #     "cctb-math-basic.yml",
    #     "cctb-sfpu-basic.yml",
    #     # "cctb-upk-basic.yml"
    #     ]
    
    rtl_args["debug_dir_path"]        = "rsim"
    rtl_args["debug_dir"]             = "debug"
    rtl_args["force"]                 = False
    rtl_args["git"]                   = "git@yyz-tensix-gitlab:tensix-hw/ws-tensix.git" # TODO: rtl_args["test_bench_dir"] and rtl_args["git"] should not be independent. 
    rtl_args["infra_dir"]             = "infra"
    rtl_args["num_processes"]         = 8
    rtl_args["project.yaml"]          = "project.yml"
    rtl_args["remote_root_dir"]       = "ws-tensix"
    rtl_args["rtl_log_file_suffix"]   = ".rtl_test.log"
    rtl_args["sim_result.yaml_key_result_val_PASS"] = "PASS"
    rtl_args["sim_result.yaml_key_result"] = "res"
    rtl_args["sim_result.yaml"]       = "sim_result.yml"
    rtl_args["src_firmware_dir_path"] = "src"
    rtl_args["src_firmware_dir"]      = "firmware"
    rtl_args["src_hd_proj_dir_path"]  = "src/hardware/tensix"
    rtl_args["src_hd_proj_dir"]       = "proj"
    rtl_args["ssh_key_file"]          = os.path.expanduser("~/.ssh/id_ed25519")
    rtl_args["test_dir_suffix"]       =  "_0"
    rtl_args["tests_dir"]             = "infra/tensix/rsim/tests"
    rtl_args["username"]              = getpass.getuser()
    rtl_args["ird_server"]            = "yyz-ird"
    rtl_args["src_dir"]               = "src"
    rtl_args["isa_file_name"]         = "assembly.yaml"

    rtl_args["local_root_dir"]        = f"from-{rtl_args['remote_root_dir']}"

    month_str =  datetime.datetime.now().strftime('%B').lower()
    day_str   = f"{datetime.datetime.now().day:02d}"
    day_str   = "01"
    path      = f"/proj_tensix/user_dev/sjaju/work/{month_str}/{day_str}"
    rtl_args["remote_root_dir_path"] = path
    rtl_args["local_root_dir_path"] = os.getcwd()
    month_str = None
    day_str = None
    del month_str
    del day_str

    rtl_utils.copy.safe_connection(host = rtl_args["ird_server"], user = rtl_args["username"], connect_kwargs = {"key_filename": rtl_args["ssh_key_file"]})

    selID, machine, port = reserve_tensix_ird_instance(
        hostname = rtl_args["ird_server"], 
        username = rtl_args["username"], 
        key = rtl_args["ssh_key_file"])

    rtl_args["hostname"]   = machine
    rtl_args["ird_sel_id"] = selID
    rtl_args["port"]       = port

    t3sim_args = dict()
    
    t3sim_args["t3sim_git_url"]         = "git@github.com:vmgeorgeTT/t3sim.git"
    t3sim_args["binutils_git_url"]      = "git@github.com:jajuTT/binutils-playground.git"
    t3sim_args["t3sim_git_branch"]      = "main" # t3sim branch
    t3sim_args["force"]                 = True # rtl_args["force"]
    t3sim_args["instruction_kind"]      = "ttqs"
    t3sim_args["t3sim_cfg_dir"]         = "cfg"
    t3sim_args["t3sim_logs_dir"]        = "logs"
    t3sim_args["start_function"]        = "main"
    t3sim_args["num_processes"]         = rtl_args["num_processes"]
    t3sim_args["t3sim_log_file_suffix"] = ".t3sim_test.log"
    t3sim_args["t3sim_inputcfg_prefix"] = "t3sim_inputcfg_"
    t3sim_args["t3sim_cfg_prefix"]      = "t3sim_cfg"

    t3sim_args["t3sim_root_dir"]    = t3sim_args["t3sim_git_url"].split("/")[-1][:-4]
    t3sim_args["binutils_root_dir"] = t3sim_args["binutils_git_url"].split("/")[-1][:-4]   
    

    # t3sim_args["assembly_yaml"]                = "assembly.yaml"
    # t3sim_args["delay"]                        = 10
    # t3sim_args["elf_files_dir"]                = rtl_args["debug_dir"].split("/")[-1] # "debug"
    # t3sim_args["enable_sync"]                  = 1

    # t3sim_args["json_log_prefix"]              = "simreport_"
    # t3sim_args["json_log_suffix"]              = ".json"
    # t3sim_args["max_num_threads_per_neo_core"] = 4
    # # t3sim_args["mop_base_addr_str"]            = "0x80d000"
    # t3sim_args["num_processes"]                = 8
    # t3sim_args["sim_dir"]                      = "t3sim"
    # t3sim_args["tensix_instructions_kind"]     = "ttqs" # todo: automatic.
    # t3sim_args["test_dir_suffix"]              = rtl_args["test_dir_suffix"] # "_0"
    # t3sim_args["debug_dir"]                    = os.path.join(rtl_args["local_test_bench_dir"], rtl_args["debug_dir"])
    # t3sim_args["cfg_dir"]                      = "cfg"
    

    check_rtl_test_bench_path_clone_and_build_if_required(path, rtl_args["remote_root_dir"], machine, port, rtl_args["username"])

    # tests, tags, suites, yml files. 
    #   options: 
    #     1. for given suits, get tags, get tests associated with these tags in yml files. 
    #     2. get all tests from yml files. 
    #     3. 

    tests = sorted(rtl_utils.test_names.get_tests(rtl_args))
    tests = [test for test in tests if "t6-quas-n4-ttx-matmul-l1-acc-multicore-height-sharded-mxfp4_a-llk" != test]
    print(f"- found {len(tests)} tests.")
    for idx, test in enumerate(tests):
        print(f"  - {idx:>{int(math.log(len(tests))) + 1}}. {test}")

    rtl_utils.rtl_tests.execute_tests(tests, rtl_args)
    t3sim_utils.t3sim_tests.clone_t3sim_and_update_assembly_yaml_if_required(rtl_args, t3sim_args)
    t3sim_utils.t3sim_tests.execute_tests(tests, rtl_args, t3sim_args)
    
    ird_release(selID)