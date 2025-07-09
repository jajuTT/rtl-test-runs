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
import re

sys.path.append("t3sim/binutils-playground/py")
import read_elf
import tensix

def sv_literal_to_int(literal: str) -> int:
    # from chatgpt
    # Convert a SystemVerilog / Verilog sized-literal such as
    #    32'h00120fff
    # to a plain Python integer.

    # Supports the four standard bases  b  o  d  h  (binary, octal, decimal,
    # hexadecimal).  Underscores are ignored.  Literals that contain  X  or  Z
    # bits raise ValueError because they cannot be mapped to a definite number.

    # >>> sv_literal_to_int("32'h00120fff")
    # 1183743
    literal = literal.strip()

    #            size      base  value
    m = re.fullmatch(r"(\d+)\'([bBoOdDhH])([0-9a-fA-F_xXzZ]+)", literal)
    if not m:
        raise ValueError(f"Not a recognised SV literal: {literal!r}")

    size_str, base_ch, value_str = m.groups()
    base_ch = base_ch.lower()

    base = {"b": 2, "o": 8, "d": 10, "h": 16}[base_ch]

    # remove visual separators
    value_str = value_str.replace("_", "")

    # refuse unknown / high-Z digits
    if re.search(r"[xXzZ]", value_str):
        raise ValueError("Literal contains X/Z bits; cannot convert to int")

    value = int(value_str, base)

    # (Optional) clip to declared width:
    width = int(size_str)
    value &= (1 << width) - 1

    return value

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

def get_tensix_instruction_kind(test, rtl_args, t3sim_args):
    key_rtl_local_root_dir_path     = "local_root_dir_path"
    key_rtl_local_root_dir          = "local_root_dir"
    key_rtl_test_dir_suffix         = "test_dir_suffix"

    for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
        assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"

    for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_t3sim_")]:
        assert key in t3sim_args.keys(), f"- error: {key} not found in given t3sim_args dict"

    test_dir_incl_path = rtl_utils.test_names.get_dir_incl_path(os.path.join(rtl_args[key_rtl_local_root_dir_path], rtl_args[key_rtl_local_root_dir]), test + rtl_args[key_rtl_test_dir_suffix])

    if not os.path.exists(test_dir_incl_path):
        raise Exception(f"- error: {test_dir_incl_path} does not exist.")

    ttx_kinds = set()
    for pwd, _, files in os.walk(test_dir_incl_path):
        for file in files:
            if file.endswith(".elf"):
                for kind in read_elf.get_instruction_kinds(os.path.join(pwd, file)):
                    if kind.is_tensix():
                        ttx_kinds.add(kind)

    if 1 != len(ttx_kinds):
        raise Exception(f"- error: expected one tensix instruction kind, received {len(ttx_kinds)}, kinds: {ttx_kinds}")

    return f"{list(ttx_kinds)[0]}"

def get_address_from_C_macro(path, file_name, macro_name):
    # file: <file>
    #   #define <name> <addr>
    # returns addr
    start_string = f"#define {macro_name}"
    file_names = rtl_utils.test_names.get_file_names_incl_path(path, file_name)
    addr = set()
    for file in file_names:
        with open(file, 'r') as fp:
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

def get_address_from_sv_file(path, file_name, var_name, prefix):
    start_string = f"{prefix}{var_name}"
    file_names = rtl_utils.test_names.get_file_names_incl_path(path, file_name)
    addr = set()
    for file in file_names:
        with open(file, 'r') as fp:
            for idx, line in enumerate(fp):
                line = line.strip()
                if line.startswith(start_string):
                    sv_addr = line.split("=")[-1][:-1]
                    addr.add(sv_literal_to_int(sv_addr))

    # TODO: make sure we find mop_cfg_base address in each of the subdirectories in `proj`

    if 0 == len(addr):
        raise Exception(f"- error: could not find string {start_string} in file {file} in directory {path}")
    elif 1 != len(addr):
        raise Exception(f"- error: expected one addr address value, received {len(addr)}. The values are: {addr}")

    return list(addr)[0]

def get_MOP_CFG_BASE_address(rtl_args):
    key_local_root_dir      = "local_root_dir"
    key_local_root_dir_path = "local_root_dir_path"
    key_src_dir             = "src_dir"

    for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
        assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"

    name = "MOP_CFG_BASE"
    file = "tt_t6_trisc_map.h"
    path = os.path.join(rtl_args[key_local_root_dir_path], rtl_args[key_local_root_dir], rtl_args[key_src_dir])

    return get_address_from_C_macro(path, file, name)

def get_IBUFFER_BASE(rtl_args):
    key_local_root_dir      = "local_root_dir"
    key_local_root_dir_path = "local_root_dir_path"
    key_src_dir             = "src_dir"

    for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
        assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"

    name = "IBUFFER_BASE"
    file = "tt_t6_trisc_map.h"
    path = os.path.join(rtl_args[key_local_root_dir_path], rtl_args[key_local_root_dir], rtl_args[key_src_dir])

    return get_address_from_C_macro(path, file, name)

def get_CFG_REGS_BASE(rtl_args):
    key_local_root_dir      = "local_root_dir"
    key_local_root_dir_path = "local_root_dir_path"
    key_src_dir             = "src_dir"

    for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
        assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"

    name = "CFG_REGS_BASE"
    file = "tt_t6_trisc_map.h"
    path = os.path.join(rtl_args[key_local_root_dir_path], rtl_args[key_local_root_dir], rtl_args[key_src_dir])

    return get_address_from_C_macro(path, file, name)

def get_TENSIX_CFG_BASE(rtl_args):
    key_local_root_dir      = "local_root_dir"
    key_local_root_dir_path = "local_root_dir_path"
    key_src_dir             = "src_dir"

    for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
        assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"

    name = "TENSIX_CFG_BASE"
    file = "tensix.h"
    path = os.path.join(rtl_args[key_local_root_dir_path], rtl_args[key_local_root_dir], rtl_args[key_src_dir])
    addr = get_address_from_C_macro(path, file, name)
    if "CFG_REGS_BASE" == addr:
        return get_CFG_REGS_BASE(rtl_args)
    else:
        raise Exception(f"- error: expected {name} address to be associated with CFG_REGS_BASE but received {addr}")

def get_CFG_REGS_END_ADDR(rtl_args):
    key_local_root_dir      = "local_root_dir"
    key_local_root_dir_path = "local_root_dir_path"
    key_src_dir             = "src_dir"

    for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
        assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"

    name = "CFG_REGS_END_ADDR"
    file = "tt_t6_trisc_regs_pkg.sv"
    path = os.path.join(rtl_args[key_local_root_dir_path], rtl_args[key_local_root_dir], rtl_args[key_src_dir])
    return hex(get_address_from_sv_file(path, file, name, "localparam integer "))

def get_CFG_OFFSET(rtl_args):
    key_local_root_dir      = "local_root_dir"
    key_local_root_dir_path = "local_root_dir_path"
    key_src_dir             = "src_dir"

    for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
        assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"

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
    path = os.path.join(rtl_args[key_local_root_dir_path], rtl_args[key_local_root_dir], rtl_args[key_src_dir])

    cfg_offsets = dict() # t3sim_name : offset
    for key, rtl_names in cfg_offset_keys.items():
        if isinstance(rtl_names, str):
            cfg_offsets[key] = int(get_address_from_C_macro(path, file, rtl_names))
        elif isinstance(rtl_names, list):
            offsets = set()
            for name in rtl_names:
                offsets.add(get_address_from_C_macro(path, file, name))

            if 0 == len(offsets):
                raise Exception(f"- error: could not find offset for {rtl_names} in file {file} in directory {path}")
            elif 1 != len(offsets):
                raise Exception(f"- error: found multiple offsets for {rtl_names} in file {file} in directory {path}, expected the offset to be same for all the macros. offsets: {offsets}")

            cfg_offsets[key] = int(list(offsets)[0])
        else:
            raise Exception(f"- error: no method defined in function get_CFG_OFFSET to parse input of type {type(rtl_names)}")

    if sorted(cfg_offsets.keys()) != sorted(cfg_offset_keys.keys()):
        raise Exception(f"- error: mismatch between cfg keys and offsets. sorted(cfg_offsets.keys()) = {sorted(cfg_offsets.keys())}, sorted(cfg_offset_keys.keys()) = {sorted(cfg_offset_keys.keys())}")

    return cfg_offsets

class cfg_engines:
    @staticmethod
    def get_mnemonics_throughputs_from_cfg_file(t3sim_args):
        key_default_cfg_file_name = "default_cfg_file_name"
        key_model_root_dir_path = "model_root_dir_path"
        key_model_root_dir = "model_root_dir"

        # for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
        #     assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_model_")]:
            assert key in t3sim_args.keys(), f"- error: {key} not found in given t3sim_args dict"

        model_dir = os.path.join(t3sim_args[key_model_root_dir_path], t3sim_args[key_model_root_dir])
        cfg_file_name = rtl_utils.test_names.get_file_name_incl_path(model_dir, t3sim_args[key_default_cfg_file_name])

        mnemonics_tpt = dict()
        with open(cfg_file_name, 'r') as file:
            data = json.load(file)

        engines_str = "engines"
        engineInstructions_str = "engineInstructions"
        tpt_str = "tpt"
        name_str = "name"
        tpt_keys_str = sorted(["int32", "bf16", "fp16", "fp32", "fp64"])

        if not engines_str in data.keys():
            raise Exception(f"- could not find key {engines_str} in file {cfg_file_name}")

        engines = data[engines_str]
        for engine in engines:
            if engineInstructions_str not in engine.keys():
                raise Exception(f"- error: could not find key {engineInstructions_str} in engine: {engine}")

            instructions = engine[engineInstructions_str]
            for instruction in instructions:
                if tpt_str not in instruction.keys():
                    raise Exception(f"- error: could not find key {tpt_str} in instruction {instruction} in engine {engine}")

                if name_str not in instruction.keys():
                    raise Exception(f"- error: could not find key {name_str} in instruction {instruction} in engine {engine}")

                tpt = instruction[tpt_str]
                if sorted(tpt.keys()) != tpt_keys_str:
                    raise Exception(f"- error: tpt key mismatch. expected: {tpt_keys_str}, received: {sorted(tpt.keys())}")

                mnemonics_tpt[instruction[name_str]] = tpt

        return mnemonics_tpt

    @staticmethod
    def get_engines_incl_mnemonics_througputs(model_args):
        key_instruction_kind = "instruction_kind"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in model_args.keys(), f"- error: {key} not found in given model_args dict"

        exe_engines = tensix.get_execution_engines_and_instructions(tensix.decoded_instruction.to_instruction_kind(model_args[key_instruction_kind]))
        mnemonics_throughputs = cfg_engines.get_mnemonics_throughputs_from_cfg_file(model_args)

        engines = []
        for engine in sorted(exe_engines.keys()):
            mnemonics = exe_engines[engine]
            ele = dict()
            mnemonics_incl_tpt = list()
            for mnemonic in sorted(mnemonics):
                if mnemonic not in mnemonics_throughputs.keys():
                    raise Exception(f"- error: could not find throughput numbers for mnemonic {mnemonic}")

                mnemonic_incl_tpt = dict()
                mnemonic_incl_tpt["name"] = mnemonic
                mnemonic_incl_tpt["tpt"] = mnemonics_throughputs[mnemonic]
                mnemonics_incl_tpt.append(mnemonic_incl_tpt)

            ele["engineName"] = engine
            ele["engineInstructions"] = mnemonics_incl_tpt

            engines.append(ele)

        return engines

    @staticmethod
    def get_engine_index(engine_name, engines):
        for idx, engine in enumerate(engines):
            if engine["engineName"] == engine_name:
                return idx

    @staticmethod
    def get_thread_ids_from_engine_name(engine_name, engines):
        engine_idx = cfg_engines.get_engine_index(engine_name, engines)
        if engine_idx is None:
            raise Exception(f"- error: could not find engine ID for engine {engine_name}")

        ids = set()
        for mnemonic_tpt in engines[engine_idx]["engineInstructions"]:
            match = re.search(r'\d+', mnemonic_tpt["name"])  # Find first occurrence of a number
            if match:
                ids.add(int(match.group()))

        return ids if (0 != len(ids)) else None

    @staticmethod
    def split_packer_unpacker(engine_name, new_engine_name_prefix, engines):
        engine_idx = cfg_engines.get_engine_index(engine_name, engines)
        thread_ids = cfg_engines.get_thread_ids_from_engine_name(engine_name, engines)
        if thread_ids is None:
            raise Exception(f"- error: could not find thread_ids for engine: {engine_name}")

        for id in sorted(thread_ids):
            engine_name = f"{new_engine_name_prefix}{id}"

            engine_mnemonics = []
            for mnemomic_tpt in engines[engine_idx]["engineInstructions"]:
                match = re.search(r'\d+', mnemomic_tpt["name"])  # Find first occurrence of a number
                if match:
                    if int(match.group()) == id:
                        engine_mnemonics.append(mnemomic_tpt)
                else:
                    engine_mnemonics.append(mnemomic_tpt)

            new_engine = dict()
            new_engine["engineName"] = engine_name
            new_engine["engineInstructions"] = engine_mnemonics

            engines.append(new_engine)

        del engines[engine_idx]

    @staticmethod
    def add_engine_groups(engines):
        for engine in engines:
            engine_grp = None
            if engine["engineName"].startswith("UNPACK"):
                engine_grp = "UNPACK"
            elif engine["engineName"].startswith("PACK"):
                engine_grp = "PACK"
            elif engine["engineName"] in ("INSTRISSUE", "INSTISSUE"):
                engine_grp = "MATH"
            else:
                engine_grp = engine["engineName"]

            engine["engineGrp"] = engine_grp

    @staticmethod
    def add_delay(model_args, engines):
        key_default_cfg_file_name = "default_cfg_file_name"
        key_model_root_dir_path = "model_root_dir_path"
        key_model_root_dir = "model_root_dir"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_t3sim_")]:
            assert key in model_args.keys(), f"- error: {key} not found in given model_args dict"

        model_dir = os.path.join(model_args[key_model_root_dir_path], model_args[key_model_root_dir])
        cfg_file_name = rtl_utils.test_names.get_file_name_incl_path(model_dir, model_args[key_default_cfg_file_name])

        with open(cfg_file_name, 'r') as file:
            data = json.load(file)

        engines_str = "engines"
        if not engines_str in data.keys():
            raise Exception(f"- error: could not find key {engines_str} in file {cfg_file_name}")

        key_engine_name = "engineName"
        key_delay = "delay"

        for df_eng in data[engines_str]:
            assert key_engine_name in df_eng.keys(), f"- error: could not find key {key_engine_name} in given engine"
            assert key_delay in df_eng.keys(), f"- error: could not find key {key_delay} in given engine"
            eng_idx = cfg_engines.get_engine_index(df_eng[key_engine_name], engines)
            if eng_idx is not None:
                engines[eng_idx][key_delay] = df_eng[key_delay]

        for eng in engines:
            assert key_delay in eng.keys(), f"- error: could not find key {key_delay} in given engine"

    @staticmethod
    def sort_engines(engines):
        new_engines = []
        eng_names = sorted(eng["engineName"] for eng in engines)
        for name in eng_names:
            idx = cfg_engines.get_engine_index(name, engines)
            new_engines.append(engines[idx])

        assert len(new_engines) == len(engines)

        return new_engines

    @staticmethod
    def get_engines(t3sim_args):

        engines = cfg_engines.get_engines_incl_mnemonics_througputs(t3sim_args)

        # split packer
        cfg_engines.split_packer_unpacker("PACK", "PACKER", engines)

        # split unpacker
        cfg_engines.split_packer_unpacker("UNPACK", "UNPACKER", engines)

        # add engine_groups
        cfg_engines.add_engine_groups(engines)

        # add delay
        cfg_engines.add_delay(t3sim_args, engines)

        # sort
        engines = cfg_engines.sort_engines(engines)

        return engines

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

            if args[key_force] or (not os.path.isdir(binutils_dir_incl_path)):
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

            if 0 == len(binutils_isa_file_incl_path): # file doesn't exist.
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
    def get_cfg(test_id, test, rtl_args, t3sim_args):
        key_rtl_local_root_dir         = "local_root_dir"
        key_rtl_local_root_dir_path    = "local_root_dir_path"
        key_rtl_rtl_tag                = "rtl_tag"
        key_rtl_test_dir_suffix        = "test_dir_suffix"
        key_t3sim_cfg_enable_shared_l1 = "cfg_enable_shared_l1"
        key_t3sim_cfg_enable_sync      = "cfg_enable_sync"
        key_t3sim_cfg_global_pointer   = "cfg_global_pointer"
        key_t3sim_cfg_latency_l1       = "cfg_latency_l1"
        key_t3sim_cfg_order_scheme     = "cfg_order_scheme"
        key_t3sim_cfg_risc_cpi         = "cfg_risc.cpi"
        key_t3sim_cfg_stack            = "cfg_stack"
        key_t3sim_instruction_kind     = "instruction_kind"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
            assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_t3sim_")]:
            assert key in t3sim_args.keys(), f"- error: {key} not found in given t3sim_args dict"

        assert t3sim_args[key_t3sim_instruction_kind] == get_tensix_instruction_kind(test, rtl_args, t3sim_args)

        cfg_dict = dict()

        cfg_dict["enableSync"]     = t3sim_args[key_t3sim_cfg_enable_sync]
        cfg_dict["arch"]           = t3sim_args[key_t3sim_instruction_kind]
        cfg_dict["llkVersionTag"]  = rtl_args[key_rtl_rtl_tag]
        cfg_dict["numTCores"]      = get_num_neos(rtl_utils.test_names.get_dir_incl_path(os.path.join(rtl_args[key_rtl_local_root_dir_path], rtl_args[key_rtl_local_root_dir]), test + rtl_args[key_rtl_test_dir_suffix]))
        cfg_dict["numTriscCores"]  = cfg_dict["numTCores"]
        cfg_dict["orderScheme"]    = t3sim_args[key_t3sim_cfg_order_scheme]
        cfg_dict["risc.cpi"]       = t3sim_args[key_t3sim_cfg_risc_cpi]
        cfg_dict["latency_l1"]     = t3sim_args[key_t3sim_cfg_latency_l1]
        cfg_dict["enableSharedL1"] = t3sim_args[key_t3sim_cfg_enable_shared_l1]
        cfg_dict["engines"]        = cfg_engines.get_engines(t3sim_args)
        cfg_dict["stack"]          = t3sim_args[key_t3sim_cfg_stack]
        cfg_dict["globalPointer"]  = t3sim_args[key_t3sim_cfg_global_pointer]
        cfg_dict["MOP_CFG_START"]  = get_MOP_CFG_BASE_address(rtl_args)
        cfg_dict["INSTR_BUFFER"]   = get_IBUFFER_BASE(rtl_args)
        cfg_dict["CFG_START"]      = get_TENSIX_CFG_BASE(rtl_args)
        cfg_dict["CFG_END"]        = get_CFG_REGS_END_ADDR(rtl_args)
        cfg_dict["CFG_OFFSET"]     = get_CFG_OFFSET(rtl_args)
        # TODO: read all the keys and corresponding values from the default cfg file.

        return cfg_dict

    @staticmethod
    def write_cfg_file(test_id, test, rtl_args, t3sim_args):
        key_t3sim_t3sim_cfg_dir        = "t3sim_cfg_dir"
        key_t3sim_t3sim_cfg_prefix     = "t3sim_cfg_prefix"
        key_t3sim_t3sim_root_dir       = "t3sim_root_dir"
        key_t3sim_t3sim_root_dir_path  = "t3sim_root_dir_path"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
            assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_t3sim_")]:
            assert key in t3sim_args.keys(), f"- error: {key} not found in given t3sim_args dict"

        cfg_dict = t3sim_tests.get_cfg(test_id, test, rtl_args, t3sim_args)
        cfg_dir_incl_path = os.path.join(t3sim_args[key_t3sim_t3sim_root_dir_path], t3sim_args[key_t3sim_t3sim_root_dir], t3sim_args[key_t3sim_t3sim_cfg_dir])
        if not os.path.isdir(cfg_dir_incl_path):
            os.makedirs(cfg_dir_incl_path, exist_ok = True)

        file_name = os.path.join(cfg_dir_incl_path, f"{t3sim_args[key_t3sim_t3sim_cfg_prefix]}{test}.json")
        with open(file_name, 'w') as file:
            json.dump(cfg_dict, file, indent = 2)

        return file_name

    @staticmethod
    def get_inputcfg(test_id, test, rtl_args, t3sim_args):
        key_rtl_local_root_dir_path     = "local_root_dir_path"
        key_rtl_local_root_dir          = "local_root_dir"
        key_rtl_test_dir_suffix         = "test_dir_suffix"
        key_t3sim_start_function        = "start_function"
        key_t3sim_t3sim_root_dir        = "t3sim_root_dir"
        key_t3sim_t3sim_cfg_dir         = "t3sim_cfg_dir"
        key_t3sim_t3sim_inputcfg_prefix = "t3sim_inputcfg_prefix"
        key_t3sim_t3sim_root_dir_path   = "t3sim_root_dir_path"

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
        input_cfg_dict["description"] = dict()
        input_cfg_dict["input"]       = dict()
        input_cfg                     = input_cfg_dict["input"]
        input_cfg["syn"]              = 0
        input_cfg["name"]             = test
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

        return input_cfg_dict

    @staticmethod
    def write_inputcfg_file(test_id, test, rtl_args, t3sim_args):
        key_t3sim_t3sim_root_dir        = "t3sim_root_dir"
        key_t3sim_t3sim_cfg_dir         = "t3sim_cfg_dir"
        key_t3sim_t3sim_inputcfg_prefix = "t3sim_inputcfg_prefix"
        key_t3sim_t3sim_root_dir_path   = "t3sim_root_dir_path"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
            assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_t3sim_")]:
            assert key in t3sim_args.keys(), f"- error: {key} not found in given rtl_args dict"

        input_cfg_dict = t3sim_tests.get_inputcfg(test_id, rtl_args, t3sim_args)

        cfg_dir_incl_path = os.path.join(t3sim_args[key_t3sim_t3sim_root_dir_path], t3sim_args[key_t3sim_t3sim_root_dir], t3sim_args[key_t3sim_t3sim_cfg_dir])
        if not os.path.isdir(cfg_dir_incl_path):
            os.makedirs(cfg_dir_incl_path, exist_ok = True)

        file_name = os.path.join(cfg_dir_incl_path, f"{t3sim_args[key_t3sim_t3sim_inputcfg_prefix]}{test}.json")
        with open(file_name, 'w') as file:
            json.dump(input_cfg_dict, file, indent = 2)

        return file_name

    @staticmethod
    def execute_test(test_id, test, rtl_args, t3sim_args):
        key_t3sim_t3sim_log_file_suffix = "t3sim_log_file_suffix"
        key_t3sim_t3sim_odir = "t3sim_odir"
        key_t3sim_t3sim_root_dir = "t3sim_root_dir"
        key_t3sim_t3sim_root_dir_path = "t3sim_root_dir_path"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_t3sim_")]:
            assert key in t3sim_args.keys(), f"- error: {key} not found in given rtl_args dict"

        inputcfg_file_name = t3sim_tests.write_inputcfg_file(test_id, test, rtl_args, t3sim_args)
        cfg_file_name = t3sim_tests.write_cfg_file(test_id, test, rtl_args, t3sim_args)

        t3sim_dir_incl_path = os.path.join(t3sim_args[key_t3sim_t3sim_root_dir_path], t3sim_args[key_t3sim_t3sim_root_dir])
        odir_incl_path = os.path.join(t3sim_dir_incl_path, t3sim_args[key_t3sim_t3sim_odir])
        log_file_name = os.path.join(odir_incl_path, f"{test}{t3sim_args[key_t3sim_t3sim_log_file_suffix]}")

        if not os.path.isdir(odir_incl_path):
            os.makedirs(odir_incl_path, exist_ok = True)

        cmds = [
            f"cd {t3sim_dir_incl_path}",
            f"python tneoSim.py --cfg {cfg_file_name} --inputcfg {inputcfg_file_name} --odir {t3sim_args[key_t3sim_t3sim_odir]}"
        ]
        cmd = " && ".join(cmds)
        print(f"- test ID: {test_id}, executing: {cmd}")

        with open(log_file_name, "w") as log_file:
            subprocess.call(
            cmd,
            shell=True,
            stdout=log_file,
            stderr=subprocess.STDOUT)

        # cmd = f"cd {t3sim_dir_incl_path} && mkdir -p {t3sim_args[key_t3sim_t3sim_odir]} && "
        # os.chdir(t3sim_dir)
        # odir = f"llk.{t3sim_args['rtl_tag']}"
        # cmd = f"mkdir -p {odir}"
        # subprocess.call(cmd.split())
        # log_file_name = f"{test}{log_file_suffix}"
        # # cmd = f"python t3sim.py --cfg {cfg_dir}/t3sim_cfg_{test}.json --inputcfg {cfg_dir}/t3sim_inputcfg_{test}.json"
        # cmd = f"python tneoSim.py --cfg {cfg_dir}/t3sim_cfg_{test}.json --inputcfg {cfg_dir}/t3sim_inputcfg_{test}.json --odir {odir}"
        # print(f"Executing t3sim test: {test}")
        # file = open(log_file_name, 'w')
        # subprocess.call(cmd.split(), stdout = file, stderr = subprocess.STDOUT)
        # os.chdir("..")

    @staticmethod
    def execute_tests(tests, rtl_args, t3sim_args):
        assert isinstance(rtl_args, dict), "- error: expected rtl_args to be a dict"
        assert isinstance(t3sim_args, dict), "- error: expected t3sim_args to be a dict"

        key_num_processes = "num_processes"
        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in rtl_args.keys(), f"- error: {key} not found in given args dict"

        for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
            assert key in t3sim_args.keys(), f"- error: {key} not found in given args dict"

        t3sim_tests.clone_t3sim_and_update_assembly_yaml_if_required(rtl_args, t3sim_args)

        num_processes = min([rtl_args[key_num_processes], t3sim_args[key_num_processes], len(tests)])
        print(f"- Number of t3sim tests to execute:                    {len(tests)}")
        print(f"- Number of parallel processes to execute t3sim tests: {num_processes}")

        with multiprocessing.Pool(processes = num_processes) as pool:
            test_results = pool.starmap(t3sim_tests.execute_test, [(idx, test, rtl_args, t3sim_args) for idx, test in enumerate(tests)])

if "__main__" == __name__:
   pass











