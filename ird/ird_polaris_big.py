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
import polaris_big_utils
import re
import rtl_utils
import shlex
import status_utils
import sys

def get_ird_reservations_list(username = getpass.getuser(), hostname = "yyz-ird", key_file_name = os.path.expanduser("~/.ssh/id_ed25519")):
    with fabric.Connection(
        hostname,
        user = username,
        connect_kwargs = {"key_filename": key_file_name}) as conn:

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

        lines = result.stdout.strip().splitlines()
        print(lines)

        if 0 == len(lines):
            return []
        elif 1 == len(lines):
            return []
        else:
            cols = re.split(r'\s{2,}', lines[0].strip())
            data = [dict(zip(cols, re.split(r'\s{2,}', line.strip()))) for line in lines[1:]]
            return data

def is_ird_instance_needed(rtl_args, polaris_big_args):
    if rtl_args["force"] or polaris_big_args["force"]:
        return True

    local_rtl_data_dir = os.path.join(rtl_args["local_root_dir_path"], rtl_args["local_root_dir"])
    if not os.path.exists(local_rtl_data_dir):
        print(f"- local RTL data directory {local_rtl_data_dir} does not exist.")
        return True

    #TODO: add more checks to determine if IRD instance is needed.

    return False


def reserve_tensix_ird_instance(username = None, hostname = "yyz-ird", machine = None, key = os.path.expanduser("~/.ssh/id_ed25519")):

    def get_ird_selection_id(username, hostname, key):
        table_dict   = get_ird_reservations_list(username = username, hostname = hostname, key_file_name = key)
        selection_id = table_dict[-1]["SELECTION ID"]
        machine      = table_dict[-1]["MACHINE"]
        port         = table_dict[-1]["SSH PORT"]

        print(f"- selection ID: {selection_id}")

        return selection_id, machine, port
        # TODO: check timestamp. For now, the assumption is ird instance is reserved and we are returning the latest one.

    if not hostname:
        raise ValueError("hostname must be specified")

    if not username:
        username = getpass.getuser()

    ird_release_all(username, hostname, key_file_name = key)

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

    selection_id, hostname, port = get_ird_selection_id(username, hostname, key)

    conn = rtl_utils.copy.safe_connection(
        host = hostname,
        user = username,
        port = port,
        connect_kwargs={"key_filename": key})

    return (selection_id, hostname, port)

def ird_release(selection_id, hostname = None, username = None):
    if not hostname:
        hostname = "yyz-ird"

    if not username:
        username = getpass.getuser()

    with fabric.Connection(hostname, user = username) as conn:
        cmd = f"ird release {selection_id}"
        print(f"- executing {cmd} on remote server {hostname}")
        conn.run(cmd)

def ird_release_all(username = getpass.getuser(), hostname = "yyz-ird", key_file_name = os.path.expanduser("~/.ssh/id_ed25519")):
    ird_list_op = get_ird_reservations_list(username, hostname, key_file_name)
    ids = sorted([int(ele['SELECTION ID']) for ele in ird_list_op])

    with fabric.Connection(
        hostname,
        user = username,
        connect_kwargs = {"key_filename": key_file_name}) as conn:

        if ids:
            cmds = [f"ird release {id}" for id in reversed(ids)]

            cmd = "; ".join(cmds)
            print(f"- executing command {cmd} on remote server {hostname}")
            result = conn.run(cmd, hide=True, warn=True)
            if result.exited:
                msg  = f"- error: could not execute {cmd} on server {hostname}.\n"
                msg += f"- command executed:   {cmd}\n"
                msg += f"- exit staus:         {result.exited}\n"
                msg += f"- messages to stdout: {result.stdout}\n"
                msg += f"- messages to stderr: {result.stderr}"
                raise Exception(msg)

        cmd = 'ird list'
        result = conn.run(cmd, hide=True, warn=True)
        if result.exited:
            msg  = f"- error: could not execute {cmd} on server {hostname}.\n"
            msg += f"- command executed:   {cmd}\n"
            msg += f"- exit staus:         {result.exited}\n"
            msg += f"- messages to stdout: {result.stdout}\n"
            msg += f"- messages to stderr: {result.stderr}"
            raise Exception(msg)
        print("- start of ird list output")
        print(result.stdout)
        print("- end of ird list output")

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
    rtl_args["yaml_files"] = {
        "ttx-llk-sfpu.yml"  : {"suites" : "postcommit"},
        "ttx-llk-fixed.yml" : {"suites" : "postcommit"}}

    # rtl_args["yaml_files"] = {
    #     "ttx-test-llk-sfpu.yml"  : {"suites" : "postcommit"},
    #     "ttx-test-llk.yml"       : {"suites" : "postcommit"}}

    rtl_args["debug_dir_path"]           = "rsim"
    rtl_args["debug_dir"]                = "debug"
    rtl_args["force"]                    = False
    rtl_args["git"]                      = "git@yyz-tensix-gitlab:tensix-hw/ws-tensix.git" # TODO: rtl_args["test_bench_dir"] and rtl_args["git"] should not be independent.
    rtl_args["infra_dir"]                = "infra"
    rtl_args["ird_server"]               = "yyz-ird"
    rtl_args["isa_file_name"]            = "assembly.yaml"
    rtl_args["max_num_threads_per_neo_core"] = 4
    rtl_args["num_processes"]            = 11
    rtl_args["project.yaml"]             = "project.yml"
    rtl_args["remote_root_dir"]          = "ws-tensix"
    rtl_args["rtl_log_file_suffix"]      = ".rtl_test.log"
    rtl_args["sim_result.yaml_key_result_val_PASS"] = "PASS"
    rtl_args["sim_result.yaml_key_result"] = "res"
    rtl_args["sim_result.yaml"]          = "sim_result.yml"
    rtl_args["src_dir"]                  = "src"
    rtl_args["src_firmware_dir_path"]    = "src"
    rtl_args["src_firmware_dir"]         = "firmware"
    rtl_args["src_hd_proj_dir_path"]     = "src/hardware/tensix"
    rtl_args["src_hd_proj_dir"]          = "proj"
    rtl_args["ssh_key_file"]             = os.path.expanduser("~/.ssh/id_ed25519")
    rtl_args["test_dir_suffix"]          =  "_0"
    rtl_args["tests_dir"]                = "infra/tensix/rsim/tests"
    rtl_args["username"]                 = getpass.getuser()
    rtl_args["num_bytes_per_register"]   = 4

    # month_str =  datetime.datetime.now().strftime('%B').lower()
    # day_str   = f"{datetime.datetime.now().day:02d}"
    # path      = f"/proj_tensix/user_dev/sjaju/work/{month_str}/{day_str}"
    # path = "/proj_tensix/user_dev/sjaju/work/feb/19"
    # path = "/proj_tensix/user_dev/sjaju/work/mar/18"
    # path = "/proj_tensix/user_dev/sjaju/work/july/01"
    path = "/proj_tensix/user_dev/sjaju/work/july/27"
    month_str = None
    day_str = None
    del month_str
    del day_str
    rtl_args["remote_root_dir_path"] = path
    rtl_args["local_root_dir_path"] = os.getcwd()
    rtl_args["rtl_tag"] = "".join(rtl_args["remote_root_dir_path"].split(os.path.sep)[-2:])
    if "july01" == rtl_args["rtl_tag"]:
        rtl_args["rtl_tag"] = "jul1"
    elif "july27" == rtl_args["rtl_tag"]:
        rtl_args["rtl_tag"] = "jul27"
    rtl_args["local_root_dir"] = f"from-{rtl_args['remote_root_dir']}-{rtl_args['rtl_tag']}"

    polaris_big_args = dict()
    polaris_big_args["cfg_enable_shared_l1"]         = 1
    polaris_big_args["cfg_enable_shared_l1"]         = 1
    polaris_big_args["cfg_enable_sync"]              = 1
    polaris_big_args["cfg_global_pointer"]           = "0xffb007f0"
    polaris_big_args["cfg_latency_l1"]               = 10.0
    polaris_big_args["cfg_order_scheme"]             = [ [0,1], [0,1], [0,2,3], [] ]
    polaris_big_args["cfg_risc.cpi"]                 = 1.0
    polaris_big_args["default_cfg_file_name"]        = f"ttqs_neo4_{rtl_args["rtl_tag"]}.json"
    polaris_big_args["force"]                        = rtl_args["force"] # rtl_args["force"]
    polaris_big_args["instruction_kind"]             = "ttqs"
    polaris_big_args["model_cfg_dir"]                = f"__config_files_{rtl_args['rtl_tag']}"
    polaris_big_args["model_cfg_file_prefix"]        = "cfg"
    polaris_big_args["model_memory_map_file_prefix"] = "memory_map"
    polaris_big_args["model_git_branch"]             = "main" # pb branch
    polaris_big_args["model_git_url"]                = "git@github.com:tenstorrent/polaris_big.git"
    polaris_big_args["model_inputcfg_file_prefix"]   = "inputcfg_"
    polaris_big_args["model_log_file_suffix"]        = ".model_test.log"
    polaris_big_args["model_logs_dir"]               = f"__logs_{rtl_args['rtl_tag']}"
    polaris_big_args["model_odir"]                   = f"__llk_{rtl_args['rtl_tag']}"
    polaris_big_args["num_processes"]                = rtl_args["num_processes"]
    polaris_big_args["start_function"]               = "main"
    polaris_big_args["cfg_stack"]                    = {
        "0": [
            "0x8023FF",
            "0x802000"
        ],
        "1": [
            "0x801FFF",
            "0x801C00"
        ],
        "2": [
            "0x801BFF",
            "0x801800"
        ],
        "3": [
            "0x8017FF",
            "0x801400"
        ]
    }

    polaris_big_args["model_root_dir"]             = polaris_big_args["model_git_url"].split("/")[-1][:-4]
    polaris_big_args["model_root_dir_path"]        = os.getcwd()
    polaris_big_args["model_instruction_sets_dir"] = "instructions_sets"
    polaris_big_args["engines_mnemonics"]          = {
        "PACKER0"   : ["PUSH_TILES"],
        "UNPACKER0" : ["POP_TILES", "UNPACR_DEST_TILE", "UNPACR_DEST_TILE_INC", "UNPACR_DEST_FACE", "UNPACR_DEST_FACE_INC", "UNPACR_DEST_ROW", "UNPACR_DEST_ROW_INC", "UNPACR_DEST_STRIDE"]}
    polaris_big_args["model_simreport"] = "simreport_"
    polaris_big_args["model_log_file_end"] = "Simreport = "
    polaris_big_args["debug"] = 15

    if os.path.exists(polaris_big_args["model_root_dir"]):
        print(f"- directory {polaris_big_args["model_root_dir"]} exists!")

    need_ird_instance = is_ird_instance_needed(rtl_args, polaris_big_args)
    print("- need_ird_instance: ", need_ird_instance)

    rtl_utils.copy.safe_connection(host = rtl_args["ird_server"], user = rtl_args["username"], connect_kwargs = {"key_filename": rtl_args["ssh_key_file"]})

    if need_ird_instance:
        selID, machine, port = reserve_tensix_ird_instance(
            hostname = rtl_args["ird_server"],
            username = rtl_args["username"],
            key = rtl_args["ssh_key_file"])
    else:
        selID = None
        machine = None
        port = None

    rtl_args["hostname"]   = machine
    rtl_args["ird_sel_id"] = selID
    rtl_args["port"]       = port

    if need_ird_instance:
        check_rtl_test_bench_path_clone_and_build_if_required(path, rtl_args["remote_root_dir"], machine, port, rtl_args["username"])

    tests = sorted(rtl_utils.test_names.get_tests(rtl_args))
    tests = [test for test in tests if "t6-quas-n4-ttx-matmul-l1-acc-multicore-height-sharded-mxfp4_a-llk" != test]
    print(f"- found {len(tests)} tests.")
    for idx, test in enumerate(sorted(tests)):
        print(f"  - {idx:>{int(math.log(len(tests))) + 1}}. {test}")

    rtl_utils.rtl_tests.execute_tests(tests, rtl_args)
    polaris_big_utils.polaris_big_tests.execute_tests(tests, rtl_args, polaris_big_args)
    status_utils.print_status(tests, rtl_args, polaris_big_args)

    if need_ird_instance:
        ird_release(selID)