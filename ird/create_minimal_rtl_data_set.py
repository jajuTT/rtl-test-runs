#!/usr/bin/env python

import getpass
import os
import re
import rtl_utils
import time
import typing

# copy regular drop from auslogo2. 
# get tests
# copy tests
# copy assembly yaml
# get memory map json

def get_rtl_data_path(rtl_tag: str) -> str:
    match rtl_tag:
        case "feb19":
            return "/proj_tensix/user_dev/sjaju/work/feb/19"
        case "mar18":
            return "/proj_tensix/user_dev/sjaju/work/mar/18"
        case "jul1":
            return "/proj_tensix/user_dev/sjaju/work/july/01"
        case "jul27":
            return "/proj_tensix/user_dev/sjaju/work/july/27"
        case "sep23":
            return "/proj_tensix/user_dev/sjaju/work/sep/23"
        case _:
            raise ValueError(f"Unknown RTL tag: {rtl_tag}")
        
# def copy_assembly_yaml(src_dir: str, dest_dir: str) -> None:
#     src_yaml = os.path.join(src_dir, "meta/instructions/yaml/assembly.yaml")
#     dest_yaml_dir = os.path.join(dest_dir, "meta/instructions/yaml")
#     dest_yaml = os.path.join(dest_yaml_dir, "assembly.yaml")
#     if not os.path.exists(src_yaml):
#         raise FileNotFoundError(f"Source assembly.yaml not found: {src_yaml}")
#     if not os.path.exists(dest_yaml_dir):
#         os.makedirs(dest_yaml_dir, exist_ok = True)
#     cmd = f"cp {src_yaml} {dest_yaml}"
#     print(f"Copying assembly.yaml: {cmd}")
#     os.system(cmd)

def get_minimal_rtl_data(rtl_args: dict[str, typing.Any], polaris_args: dict[str, typing.Any]) -> None:

    assert isinstance(rtl_args, dict), "rtl_args must be a dictionary"
    assert isinstance(polaris_args, dict), "polaris_args must be a dictionary"
    key_local_root_dir = "local_root_dir"
    key_local_root_dir_path = "local_root_dir_path"
    key_debug_dir_path = "debug_dir_path"
    key_debug_dir = "debug_dir"
    key_rtl_tag = "rtl_tag"
    key_test_dir_suffix = "test_dir_suffix"

    for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
        assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"
            
    src_dir = os.path.join(rtl_args[key_local_root_dir_path], rtl_args[key_local_root_dir])
    if not os.path.exists(src_dir):
        raise FileNotFoundError(f"Source directory {src_dir} does not exist")
    
    if not src_dir.endswith("/"):
        src_dir += "/"
    
    rtl_tag = rtl_args[key_rtl_tag]
    if not rtl_tag:
        raise ValueError("rtl_tag is required in rtl_args")
    
    dest_dir_path = "__ext/rtl_test_data_set"
    dest_dir = os.path.join(dest_dir_path, rtl_tag)

    # copy assembly.yaml and other directories.
    cmd = f"rsync -avz --include='*/' --include='meta/instructions/yaml/assembly.yaml' --exclude='*' --prune-empty-dirs {src_dir} {dest_dir}"
    print(f"Executing command: {cmd}")
    os.system(cmd)

    test_dir_parent_rel_path = os.path.join(rtl_args[key_debug_dir_path], rtl_args[key_debug_dir])

    # copy tests
    tests = rtl_utils.test_names.get_tests(rtl_args)
    for test in tests:
        test_path = os.path.join(test_dir_parent_rel_path, test + rtl_args.get(key_test_dir_suffix, "_0"))
        test_path = re.escape(test_path)
        cmd = f"rsync -avz --include='*/' "
        cmd += f"--include='{test_path}/**/*.elf' --include='sim_result.yml' "
        cmd += f"--exclude='*' --prune-empty-dirs {src_dir} {dest_dir}"

        print(f"Executing command: {cmd}")
        os.system(cmd)

    # minimal_rtl_data_prefix = "__ext/rtl_test_data_set/"
    # rtl_tag = rtl_args.get("rtl_tag", "")
    # if not rtl_tag:
    #     raise ValueError("rtl_tag is required in rtl_args")
    
    # rtl_data_path = os.path.join(minimal_rtl_data_prefix, rtl_tag)
    # if os.path.exists(rtl_data_path):
    #     print(f"Minimal RTL data already exists at {rtl_data_path}. Skipping copy.")
    #     return
    
    # if not os.path.exists(minimal_rtl_data_prefix):
    #     os.makedirs(minimal_rtl_data_prefix, exist_ok = True)

    # src_dir = os.path.join(rtl_args[key_])

    


def main():
    rtl_tags = ["feb19", "mar18", "jul1", "jul27", "sep23"]
    # rtl_tags = ["feb19"]

    minimal_rtl_data_set_dir = "__ext/rtl_test_data_set"

    for tag in rtl_tags:
        print(f"Processing RTL tag: {tag}")
        src_dir = get_rtl_data_path(tag)
        dest_dir = os.path.join(minimal_rtl_data_set_dir, tag)
        if not dest_dir.endswith("/"):
            dest_dir += "/"

        if not src_dir.endswith("/"):
            src_dir += "/"

        os.makedirs(dest_dir, exist_ok = True)

        cmd = f"rsync -avz --include='*/' --include='meta/instructions/yaml/assembly.yaml' --exclude='*' --prune-empty-dirs auslogo2:{src_dir} {dest_dir}"
        print(f"Executing command: {cmd}")
        os.system(cmd)

        tests_file = f"llk_tests_{tag}.txt"
        if not os.path.isfile(tests_file):
            raise FileNotFoundError(f"Tests file {tests_file} not found.")
        tests: list[str] = []
        with open(tests_file, "r") as f:
            tests = f.readlines()
            print(f"Found {len(tests)} tests for tag {tag}.")

        if "feb19" == tag:
            tests = ["rsim/debug/" + test.strip() for test in tests]
        else:
            tests = [test.strip() for test in tests]

        cmd = f"rsync -avz --include='*/' "
        for test in tests:
            test += "_0"
            test = re.escape(test)
            cmd += f"--include='{test}/**/*.elf' --include='{test}/sim_result.yml' "
            
        cmd += f"--exclude='*' --prune-empty-dirs auslogo2:{src_dir} {dest_dir}"
        print(f"Executing command: {cmd}")
        os.system(cmd)

        # # os.system(f"rsync -az --include='*/' --include='*.elf' --include='meta/instructions/yaml/assembly.yaml' --include='sim_result.yml' --exclude='*' auslogo2:{source} {dest}")
        # # --prune-empty-dirs

if "__main__" == __name__:
    main()
        