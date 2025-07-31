#!/usr/bin/env python

from fileinput import filename
import os
import sys
import json

def get_cfg_defines_from_file(file_path):
    cfg_defines = dict()
    with open(file_path, 'r') as f:
        for line in f:
            if line.startswith('#define'):
                parts = line.split()
                if len(parts) >= 3:
                    key = parts[1]
                    value = ' '.join(parts[2:])
                    cfg_defines[key] = value
    return cfg_defines

def get_cfg_defines_file_path():
    cfg_defines_file = "cfg_defines.h"
    file_paths = []
    for pwd, _, files in os.walk('.'):
        for file in files:
            if "cfg_defines.h" == file:
                file_paths.append(os.path.join(pwd, file))
    return sorted(file_paths)

def get_cfg_defines():
    file_paths = get_cfg_defines_file_path()
    if not file_paths:
        print("No cfg_defines.h files found.")
        return {}
    
    cfg_defines0 = get_cfg_defines_from_file(file_paths[0])
    if len(file_paths) > 1:
        for file in file_paths[1:]:
            cfg_defines = get_cfg_defines_from_file(file)
            if cfg_defines != cfg_defines0:
                print(f"Warning: Multiple cfg_defines.h files found with different contents: {file_paths}")
    return cfg_defines0

def get_registers_addresses_from_cfg_defines():
    cfg_defines = get_cfg_defines()
    registers = dict()
    for key, value in cfg_defines.items():
        if key.endswith('ADDR32'):
            registers[key] = int(value)
    return registers

def get_addresses_registers_from_cfg_defines():
    regs_addrs = get_registers_addresses_from_cfg_defines()
    addrs_regs = {value : [] for value in sorted(set(regs_addrs.values()))}
    for addr in addrs_regs.keys():
        for key, value in regs_addrs.items():
            if value == addr:
                addrs_regs[addr].append(key)

    for addr in addrs_regs.keys():
        addrs_regs[addr].sort()

    return addrs_regs

def get_one_register_name_per_address_from_cfg_defines():
    addrs_regs = get_addresses_registers_from_cfg_defines()
    one_reg_per_addr = {regs[0] : addr for addr, regs in addrs_regs.items() if regs}
    assert len(one_reg_per_addr) == len(addrs_regs), "Not all addresses have a single register associated with them."
    return one_reg_per_addr

def write_registers_addresses_to_file(filename):
    regs_addrs = get_one_register_name_per_address_from_cfg_defines()
    dict_to_write = {"CFG_REGISTER_OFFSETS" : regs_addrs}
    with open(filename, 'w') as f:
        json.dump(dict_to_write, f, indent = 2)

def identify_missing_addresses_in_cfg_defines():
    addrs_regs = get_addresses_registers_from_cfg_defines()
    min_addr = min(addrs_regs.keys())
    max_addr = max(addrs_regs.keys())
    print("+ CFG registers addresses range:", min_addr, "to", max_addr)

    missing_addrs = [addr for addr in range(min_addr, max_addr + 1) if addr not in addrs_regs.keys()]
    if missing_addrs:
        print("  - Missing addresses in cfg_defines:", missing_addrs)
    else:
        print("  - No missing addresses found in cfg_defines.")

if "__main__" == __name__:
    write_registers_addresses_to_file("cfg_register_offsets.json")
    identify_missing_addresses_in_cfg_defines()
    # regs_addrs = get_registers_addresses_from_cfg_defines()
    # print(len(regs_addrs), "registers found with ADDR32")
    # for key, value in regs_addrs.items():
    #     print(f"{key}: {value}")

    # addrs_regs = get_addresses_registers_from_cfg_defines()
    # for key, value in addrs_regs.items():
    #     print(f"{key}: {value}")