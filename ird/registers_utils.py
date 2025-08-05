#!/usr/bin/env python

import math
import bs4
import json
import os
import re
import sys
import copy

def to_int(value):
    if isinstance(value, int):
        return value
    elif isinstance(value, str):
        if value.startswith('0x') or value.startswith('0X'):
            return int(value, 16)

        if value.startswith('0b') or value.startswith('0B'):
            return int(value, 2)

        if value.startswith('0o') or value.startswith('0O'):
            return int(value, 8)

        if value.isdigit():
            return int(value)

        raise ValueError(f"Invalid string for conversion to int: {value}")

    raise ValueError(f"Unsupported type for conversion: {type(value)}")

def get_files_from_path(path, name=None, extension=None):
    files = []
    for root, _, filenames in os.walk(path):
        for file in filenames:
            if extension is None or file.endswith(extension):
                if name is None or name in file:
                    files.append(os.path.join(root, file))
    return sorted(files)

def parse_html_file(file_name):
    if not os.path.exists(file_name):
        raise FileNotFoundError(f"HTML file '{file_name}' does not exist.")

    with open(file_name, 'r') as f:
        content = f.read()

    soup = bs4.BeautifulSoup(content, 'html.parser')
    return soup

def resides_within_range(ele, start, end):
    return ele >= start and ele <= end

def is_within_range(ele, start, end):
    return resides_within_range(ele, start, end)

def get_dependency_map_from_address_map(address_map):
    dep_map = {}
    for idx0, ele0 in enumerate(address_map):
        dep_map[idx0] = []
        for idx1, ele1 in enumerate(address_map):
            if idx0 == idx1:
                continue
            if resides_within_range(ele0['START'], ele1['START'], ele1['END']) and resides_within_range(ele0['END'], ele1['START'], ele1['END']):
                dep_map[idx0].append(idx1)

    for idx, deps in dep_map.items():
        if len(deps) > 1:
            sorted_deps = sorted(deps, key=lambda x: address_map[x]['END'] - address_map[x]['START'], reverse = True)
            dep_map[idx] = sorted_deps

    return dep_map

def parse_table0(table):
    addr_map = []
    table_entries = table.find_all('td', class_='data')
    for cell in table_entries:
        key = cell.get_text().strip()
        row = cell.parent
        bit_data_cell = row.find('td', class_='bit_data')
        address_text = bit_data_cell.get_text().strip()

        if "-" in address_text:
            match = re.match(r'(0x[0-9A-F]+)\s*-\s*(0x[0-9A-F]+)', address_text)
            if match:
                start_addr = to_int(match.group(1))
                end_addr = to_int(match.group(2))
                addr_map.append({"KEY": key, "START": start_addr, "END": end_addr})
        else:
            raise Exception(f"Address format not recognized: {address_text} for key {key}")

    if not addr_map:
        raise ValueError("No valid address ranges found in the HTML table.")

    dep_map = get_dependency_map_from_address_map(addr_map)
    new_addr_map = copy.deepcopy(addr_map)
    for idx, map in enumerate(addr_map):
        if map['KEY'].startswith('...'):
            assert dep_map[idx], f"Could not find dependencies for key {map['KEY']}"
            prefix = ".".join([addr_map[dep]['KEY'].strip().lstrip('.').strip() for dep in dep_map[idx]])
            new_addr_map[idx]['KEY'] = prefix + "." + map['KEY'].strip().lstrip('.').strip()

    new_addr_map.sort(key=lambda x: x['START'])
    new_addr_map_dict = {ele['KEY']: ele for ele in new_addr_map}
    assert len(new_addr_map_dict) == len(new_addr_map), "Duplicate keys found in the new map."
    return new_addr_map_dict

def add_register_to_address_map(register_name, register_address, address_map):
    possible_regions = [(key, value['END'] - value['START']) for key, value in address_map.items() if is_within_range(register_address, value['START'], value['END'])]
    if not possible_regions:
        raise ValueError(f"No address range found for register {register_name} with address {register_address}. Possible matches: {possible_regions}")
    min_size = min(size for _, size in possible_regions)
    smallest_region = [key for key, size in possible_regions if size == min_size]
    if len(smallest_region) > 1:
        raise ValueError(f"Multiple address ranges found for register {register_name} with address {register_address}. Possible matches: {possible_regions}. Smallest regions: {smallest_region}")
    smallest_region = smallest_region[0]
    if 'REGISTERS' not in address_map[smallest_region]:
        address_map[smallest_region]['REGISTERS'] = dict()

    if register_name in address_map[smallest_region]['REGISTERS']:
        raise ValueError(f"Duplicate register name '{register_name}' found in address range {smallest_region}. Previous address: {hex(address_map[smallest_region]['REGISTERS'][register_name])}, New address: {hex(register_address)}")

    address_map[smallest_region]['REGISTERS'][register_name] = register_address

def add_registers_to_address_map(regs, address_map):
    for name, address in regs.items():
        add_register_to_address_map(name, address, address_map)

def parse_registers_from_table(table, address_map):
    table_entries = table.find_all('td', class_='data')
    for cell in table_entries:
        key = cell.get_text().strip()
        row = cell.parent
        bit_data_cell = row.find('td', class_='bit_data')
        address_text = bit_data_cell.get_text().strip()

        if "-" not in address_text:
            match = re.match(r'(0x[0-9A-Fa-f]+)', address_text)
            if match:
                address = to_int(match.group(1))
                add_register_to_address_map(key, address, address_map)

def parse_soup(soup):
    tbls = soup.find_all('table')
    print(f"Found {len(tbls)} tables in the HTML file.")
    if not tbls:
        raise ValueError("No data cells found in the HTML table.")

    tbl0_addr_map = parse_table0(tbls[0])
    print("Parsed address map from HTML table.")

    if len(tbls) <= 1:
        return tbl0_addr_map

    for idx, tbl in enumerate(tbls[1:]):
        if not tbl:
            continue
        print(f"Processing table {idx} with {len(tbl)} entries.")
        parse_registers_from_table(tbl, tbl0_addr_map)

    for value in tbl0_addr_map.values():
        if 'REGISTERS' in value.keys():
            value['REGISTERS'] = dict(sorted(value['REGISTERS'].items(), key=lambda item: item[1]))

    print("Finished parsing all tables.")
    return tbl0_addr_map

def get_addresses_from_html_file(file_name):
    if not os.path.exists(file_name):
        raise FileNotFoundError(f"HTML file '{file_name}' does not exist.")

    soup = parse_html_file(file_name)
    addrs = parse_soup(soup)

    return addrs

def get_addresses_from_html_files(file_names):
    if not file_names:
        raise ValueError("No file_names provided to get addresses from.")

    if isinstance(file_names, str):
        file_names = [file_names]

    if not isinstance(file_names, list):
        raise TypeError("Files should be a list of file paths or a single file path as a string.")

    if not file_names:
        raise ValueError("No file_names found in the provided path.")

    if not os.path.exists(file_names[0]):
        raise FileNotFoundError(f"File '{file_names[0]}' does not exist.")

    addrs0 = get_addresses_from_html_file(file_names[0])
    if not addrs0:
        raise ValueError(f"No addresses found in the file: {file_names[0]}")

    if len(file_names) > 1:
        for file in file_names[1:]:
            if not os.path.exists(file):
                raise FileNotFoundError(f"File '{file}' does not exist.")

            addrs = get_addresses_from_html_file(file)
            if addrs != addrs0:
                msg = f"Warning: Addresses in {file} differ from the first file {file_names[0]}."
                raise Exception(msg)

    return addrs0

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

def get_cfg_defines_file_path(path):
    cfg_defines_file = "cfg_defines.h"
    file_paths = []
    for pwd, _, files in os.walk(path):
        for file in files:
            if "cfg_defines.h" == file:
                file_paths.append(os.path.join(pwd, file))
    print(f"Found {len(file_paths)} cfg_defines.h files.")
    print("Paths:", file_paths)
    return sorted(file_paths)

def get_cfg_defines(path='.'):
    file_paths = get_cfg_defines_file_path(path)
    if not file_paths:
        print("No cfg_defines.h files found.")
        return {}

    cfg_defines0 = get_cfg_defines_from_file(file_paths[0])
    if len(file_paths) > 1:
        for file in file_paths[1:]:
            cfg_defines = get_cfg_defines_from_file(file)
            assert cfg_defines == cfg_defines0, f"Warning: Multiple cfg_defines.h files found with different contents: {file_paths}"
    return cfg_defines0

def get_registers_addresses_from_cfg_defines(path):
    cfg_defines = get_cfg_defines(path)
    registers = dict()
    for key, value in cfg_defines.items():
        if key.endswith('ADDR32'):
            registers[key] = int(value)
    return registers

def get_addresses_registers_from_cfg_defines(path):
    regs_addrs = get_registers_addresses_from_cfg_defines(path)
    addrs_regs = {value : [] for value in sorted(set(regs_addrs.values()))}
    for addr in addrs_regs.keys():
        for key, value in regs_addrs.items():
            if value == addr:
                addrs_regs[addr].append(key)

    for addr in addrs_regs.keys():
        addrs_regs[addr].sort()

    return addrs_regs

def get_one_register_name_per_address_from_cfg_defines(path):
    addrs_regs = get_addresses_registers_from_cfg_defines(path)
    one_reg_per_addr = {regs[0] : addr for addr, regs in addrs_regs.items() if regs}
    assert len(one_reg_per_addr) == len(addrs_regs), "Not all addresses have a single register associated with them."
    return one_reg_per_addr

def write_registers_addresses_to_file(path, filename):
    regs_addrs = get_one_register_name_per_address_from_cfg_defines(path)
    dict_to_write = {"CFG_REGISTER_OFFSETS" : regs_addrs}
    with open(filename, 'w') as f:
        json.dump(dict_to_write, f, indent = 2)

def identify_missing_addresses_in_cfg_defines(path):
    addrs_regs = get_addresses_registers_from_cfg_defines(path)
    min_addr = min(addrs_regs.keys())
    max_addr = max(addrs_regs.keys())
    print("+ CFG registers addresses range:", min_addr, "to", max_addr)

    missing_addrs = [addr for addr in range(min_addr, max_addr + 1) if addr not in addrs_regs.keys()]
    if missing_addrs:
        print("  - Missing addresses in cfg_defines:", missing_addrs)
    else:
        print("  - No missing addresses found in cfg_defines.")

def get_trisc_address_map(path):
    html_file = "TriscAddressMap.html"
    files_incl_path = get_files_from_path(path, name = html_file)
    print(f"Found {len(files_incl_path)} TriscAddressMap.html files in the path: {path}")
    addrs = get_addresses_from_html_files(files_incl_path)

    cfg_offsets = get_one_register_name_per_address_from_cfg_defines(path)
    addrs['cfg_regs']['OFFSETS'] = cfg_offsets

    return addrs

def add_num_bytes_per_registers(mem_map, num_bytes_per_register):
    for key, value in mem_map.items():
        if 'START' in value and 'END' in value:
            start = value['START']
            end = value['END']
            if start % num_bytes_per_register != 0 or (end + 1) % num_bytes_per_register != 0:
                raise ValueError(f"Start or end address for {key} is not aligned to {num_bytes_per_register} bytes: {start}, {end}")
            if 'REGISTERS' in value:
                for reg_name, reg_addr in value['REGISTERS'].items():
                    if reg_addr % num_bytes_per_register != 0:
                        raise ValueError(f"Register address {reg_addr} for {reg_name} in {key} is not aligned to {num_bytes_per_register} bytes.")
            value['NUM_BYTES_PER_REGISTER'] = num_bytes_per_register

    return mem_map

def get_trisc_address_map_incl_reg_size(path, num_bytes_per_register):
    addrs = get_trisc_address_map(path)
    add_num_bytes_per_registers(addrs, num_bytes_per_register)

    return addrs

def get_cluster_map(path, num_bytes_per_register):
    html_file = "NocAddressMap.html"

    files_incl_path  = get_files_from_path(path, name = html_file)
    n1_cluster_files = [file for file in files_incl_path if "n1" in file]
    n4_cluster_files = [file for file in files_incl_path if "n4" in file]
    assert sorted(n1_cluster_files + n4_cluster_files) == sorted(files_incl_path)

    addrs = dict()
    addrs['n1_cluster_map'] = add_num_bytes_per_registers(get_addresses_from_html_files(n1_cluster_files), num_bytes_per_register)
    addrs['n4_cluster_map'] = add_num_bytes_per_registers(get_addresses_from_html_files(n4_cluster_files), num_bytes_per_register)

    return addrs

def get_memory_map(path, num_bytes_per_register):
    mem_map = dict()
    mem_map['trisc_map'] = get_trisc_address_map_incl_reg_size(path, num_bytes_per_register)
    cluster_map = get_cluster_map(path, num_bytes_per_register)
    for key, value in cluster_map.items():
        mem_map[key] = value

    return mem_map

def change_addresses_to_hex(mem_map):
    for key0, value0 in mem_map.items():
        for key1, value1 in value0.items():
            for key2, value2 in value1.items():
                if key2 in ['START', 'END']:
                    mem_map[key0][key1][key2] = hex(value2)
                if key2 == "REGISTERS":
                    for key3, value3 in value2.items():
                        mem_map[key0][key1][key2][key3] = hex(value3)

    return mem_map

def write_memory_map(path, num_bytes_per_register, file_to_write):
    mem_map = get_memory_map(path, num_bytes_per_register)
    mem_map = change_addresses_to_hex(mem_map)
    with open(file_to_write, 'w') as f:
        json.dump(mem_map, f, indent = 2)

if "__main__" == __name__:
    write_memory_map(sys.argv[1], 4, "memory_map.json")
