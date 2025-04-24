#!/usr/bin/env python

import collections
import itertools

import sys
sys.path.append("t3sim/binutils-playground/py") # todo: remove hardcoding.
import read_elf

# https://stackoverflow.com/a/287944/27310047
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class test_results:
    def __init__(self):
        self.status = None
        self.num_cycles = None

    def __str__(self):
        msg  = ""
        msg += f"+ Status:           {self.status}\n"
        msg += f"+ Number of cycles: {self.num_cycles}"

        return msg

    def __repr__(self):
        return self.__str__()

class elf_file(collections.defaultdict):
    def __init__(self):
        super().__init__(elf_file)

    def __getattr__(self, name):
        return self[name]

    def __getitem__(self, key):
        return super().__getitem__(key)

    def __str__(self):
        return f"elf_file({dict(self)})"

    def __repr__(self):
        return f"elf_file({dict(self)})"

class elf_file_indices:
    def __init__(self):
        self.ttx        = []
        self.core_id0s  = []
        self.core_id1s  = []
        self.neo_ids    = []
        self.thread_ids = []

class test_status:
    def __init__(self):
        self.name             = None
        self.rtl              = test_results() # rtl_status
        self.pm               = test_results() # performance_model_status
        self.elf              = elf_file()
        self.elf_file_indices = elf_file_indices()

    def __str__(self):
        # def traverse_elf(elf, msg, path = ""):
        #     def traverse_elf_to_msg_list(elf, msg_list, path):
        #         if isinstance(elf, elf_file):
        #             for key, value in elf.items():
        #                 traverse_elf_to_msg_list(value, msg_list, f"{path}.{key}")
        #         elif isinstance(elf, tuple):
        #             msg_list[0] += "  " + path + "\n"
        #             msg_list[0] += read_elf.instructions.instruction_histogram_to_str(elf[0], "", preemble = path, print_offset = 4)

        #     msg_list = [""]
        #     traverse_elf_to_msg_list(elf, msg_list, path)
        #     msg += msg_list[0]

        #     return msg

        def instruction_profile_to_str(elf_ips, elf_file_indices):
            import os

            msg = ''
            for ttx_name, core_id0, core_id1, neo_id, thread_id in itertools.product(elf_file_indices.ttx, elf_file_indices.core_id0s, elf_file_indices.core_id1s, elf_file_indices.neo_ids, elf_file_indices.thread_ids):
                ip = elf_ips[ttx_name].core[core_id0][core_id1].neo[neo_id].thread[thread_id]
                path = os.path.join("ttx", ttx_name, f"core_{core_id0:02d}_{core_id1:02d}", f"neo_{neo_id}", f"thread_{thread_id}", "out", f"thread_{thread_id}.elf")
                msg += "  " + path + "\n"
                msg += read_elf.instructions.instruction_histogram_to_str(ip[0], "", preemble = path, print_offset = 4)

            return msg.rstrip()


        msg  = ""
        msg += f"+ Test name: {self.name}\n"
        msg += "+ RTL status: \n"
        msg += f"{self.rtl}"
        msg += "\n"
        msg += "+ Performance model status: \n"
        msg += f"{self.pm}"
        msg += "\n"
        msg += "+ Instruction profile from ELF file: \n"
        msg += instruction_profile_to_str(self.elf, self.elf_file_indices)
        return msg

    def __repr__(self):
        return self.__str__()
    
    def get_num_instructions(self):
        def get_num_instructions_from_profile(instruction_profile, num_instructions):
            if all(isinstance(ele, read_elf.instructions.kind) for ele in instruction_profile.keys()):
                for instr_kind, num_instrs in instruction_profile.items():
                    if instr_kind not in num_instructions.keys():
                        num_instructions.update({instr_kind : 0})

                    for instr in num_instrs.keys():
                        num_instructions[instr_kind] += num_instrs[instr][0]

            else:
                for value in instruction_profile.values():
                    if isinstance(value, dict):
                        get_num_instructions_from_profile(value, num_instructions)
                                
        num_instructions = dict()
        for ttx_name, core_id0, core_id1, neo_id, thread_id in itertools.product(self.elf_file_indices.ttx, self.elf_file_indices.core_id0s, self.elf_file_indices.core_id1s, self.elf_file_indices.neo_ids, self.elf_file_indices.thread_ids):
            ip = self.elf[ttx_name].core[core_id0][core_id1].neo[neo_id].thread[thread_id]
            get_num_instructions_from_profile(ip[0], num_instructions)

        return num_instructions
    
    def get_instruction_kinds(self):
        def get_instruction_kinds_from_profile(instruction_profile, instruction_kinds):
            if all(isinstance(ele, read_elf.instructions.kind) for ele in instruction_profile.keys()):
                for instr_kind, num_instrs in instruction_profile.items():
                    instruction_kinds.add(instr_kind)

            else:
                for value in instruction_profile.values():
                    if isinstance(value, dict):
                        get_instruction_kinds_from_profile(value, instruction_kinds)
                                
        instruction_kinds = set()
        for ttx_name, core_id0, core_id1, neo_id, thread_id in itertools.product(self.elf_file_indices.ttx, self.elf_file_indices.core_id0s, self.elf_file_indices.core_id1s, self.elf_file_indices.neo_ids, self.elf_file_indices.thread_ids):
            ip = self.elf[ttx_name].core[core_id0][core_id1].neo[neo_id].thread[thread_id]
            get_instruction_kinds_from_profile(ip[0], instruction_kinds)

        return instruction_kinds


def to_matrix_str(strings, num_columns, offset = 2):
    def to_str (strings, num_columns, offset):
        import copy
        str_list = copy.deepcopy(strings)
        # Step 1: Determine the number of rows
        num_rows = -(-len(str_list) // num_columns)  # Ceiling division

        # Step 2: Pad the list to make it fit the matrix structure
        str_list += [''] * (num_rows * num_columns - len(str_list))  # Fill empty spots

        # Step 3: Rearrange the list into columns
        columns = [str_list[i::num_columns] for i in range(num_columns)]

        # Step 4: Find the max width of each column
        col_widths = [max(len(word.strip()) for word in col) for col in columns]

        # Step 5: Print the matrix row-wise
        msg = ''
        for row in zip(*columns):
            msg += f"{' ' * offset}{'  '.join(word.strip().ljust(width) for word, width in zip(row, col_widths))}\n"

        return msg.rstrip()

    if isinstance(strings, set):
        strings = sorted(list(strings))

    return to_str(strings, num_columns, offset)

def print_str_list_as_matrix(str_list, num_columns = 5, print_offset = 2):
    if isinstance(str_list, set):
        str_list = sorted(list(str_list))

    print(to_matrix_str(str_list, num_columns, print_offset))

def get_status(test_names, status_args):
    import os

    root_dir              = status_args["root_dir"]              if "root_dir"              in status_args.keys() else os.path.dirname(os.path.abspath(__file__))
    debug_dir             = status_args["debug_dir"]             if "debug_dir"             in status_args.keys() else "debug"
    t3sim_dir             = status_args["t3sim_dir"]             if "t3sim_dir"             in status_args.keys() else "t3sim"
    sim_result_yml        = status_args["sim_result_yml"]        if "sim_result_yml"        in status_args.keys() else "sim_result.yml"
    flatten_dict          = status_args["flatten_dict"]          if "flatten_dict"          in status_args.keys() else False
    test_dir_suffix       = status_args["test_dir_suffix"]       if "test_dir_suffix"       in status_args.keys() else "_0"
    rtl_log_file_suffix   = status_args["rtl_log_file_suffix"]   if "rtl_log_file_suffix"   in status_args.keys() else ".rtl_test.log"
    t3sim_log_file_suffix = status_args["rtl_log_file_suffix"]   if "t3sim_log_file_suffix" in status_args.keys() else ".t3sim_test.log"
    assembly_yaml         = status_args["assembly_yaml"]         if "assembly_yaml"         in status_args.keys() else "t3sim/binutils-playground/instruction_sets/ttqs/assembly.yaml" # remove hardcoding.

    if not os.path.exists(root_dir):
        raise Exception(f"- error: given root directory does not exist. given root directory: {root_dir}")

    if (not assembly_yaml) or (not os.path.isfile(assembly_yaml)):
        raise Exception(f"- error: could not find file {assembly_yaml}")

    def get_rtl_status_of_test(test, root_dir, debug_dir, sim_result_yml, test_dir_suffix, rtl_status):

        # check if sim_result_yml file exists. if it does, then read status from there.
        # if sim_result_yml does not exist, check the log file.
        # from log file check if it is exception or not implemented error.

        def get_sim_result_yml_incl_path(test, root_dir, debug_dir, test_dir_suffix, sim_result_yml):
            import os

            yml_incl_path = os.path.join(root_dir, debug_dir, test + test_dir_suffix, sim_result_yml)

            return yml_incl_path

        def get_rtl_status_from_sim_result_yml(test, root_dir, debug_dir, test_dir_suffix, sim_result_yml, rtl_status):
            import os
            import yaml

            sim_result_incl_path = get_sim_result_yml_incl_path(test, root_dir, debug_dir, test_dir_suffix, sim_result_yml)

            if os.path.isfile(sim_result_incl_path):
                with open(sim_result_incl_path) as stream:
                    yml = yaml.safe_load(stream)
                    rtl_status.status = yml['res']
                    rtl_status.num_cycles = yml['total-cycles']
                    return True
            else:
                return False

        def get_rtl_status_from_log_file(test, root_dir, rtl_status):
            import os
            log_file = os.path.join(root_dir, test + ".rtl_test.log")
            log_file = os.path.join(root_dir, debug_dir, test + test_dir_suffix, test + ".rtl_test.log")

            if not os.path.isfile(log_file):
                raise Exception(f"- error: could not find file {log_file} associated with test {test}")

            with open(log_file) as file:
                lines = file.readlines()
                if not lines:
                    # raise Exception(f"- {file_name} is empty!")
                    return

            # last_line = lines[-1].rstrip()
            words_from_last_line = lines[-1].rstrip().split()
            if words_from_last_line:
                if words_from_last_line[0] in ("Exception:", "NotImplementedError:"):
                    rtl_status.status = words_from_last_line[0][0:-1]
                    return True

            return False

        if get_rtl_status_from_sim_result_yml(test, root_dir, debug_dir, test_dir_suffix, sim_result_yml, rtl_status):
            return True
        else:
            return get_rtl_status_from_log_file(test, root_dir, rtl_status)

    def get_instruction_set (ttqs_assembly_yaml):
        instruction_set = dict()
        instruction_set.update({read_elf.instructions.kind.ttqs : ttqs_assembly_yaml}) # todo: remove hardcoding
        return instruction_set

    def get_instruction_profile_from_elf_file(test, root_dir, debug_dir, elf_files, elf_file_indices, instruction_set, flatten_dict):
        def get_indices_from_path(path):
            import re
            # 1. Extract the second part (kernels)
            match1 = re.search(r'ttx/([^/]+)/', path)
            kf = match1.group(1) if match1 else None # kernels/firmwares

            # 2. Extract the [0][0] associated with `core`
            match2 = re.search(r'core_(\d+)_(\d+)', path)
            core_ids = [int(ele) for ele in match2.groups()] if match2 else None # core_00_00

            # 3. Extract the id `0`` associated with `neo``
            match3 = re.search(r'neo_(\d+)', path)
            neo_id = int(match3.group(1)) if match3 else None

            # 4. Extract the id `2` associated with `thread`
            match4 = re.findall(r'thread_(\d+)', path)
            thread_ids = [int(ele) for ele in match4] if match4 else None

            if thread_ids:
                thread_ids = int(thread_ids[0]) if thread_ids.count(thread_ids[0]) == len(thread_ids) else None

            return kf, core_ids, neo_id, thread_ids

        import os
        test_dir = os.path.join(root_dir, debug_dir, test + "_0")
        if os.path.isdir(test_dir):
            ttx_dir = os.path.join(test_dir, "ttx")
            os_walk = os.walk(ttx_dir)
            for pwd, _, files in os_walk:
                for file in files:
                    if file.endswith(".elf"):
                        file_name_incl_path = os.path.join(pwd, file)
                        indices = get_indices_from_path(file_name_incl_path)
                        kf        = indices[0]
                        core_id0  = indices[1][0]
                        core_id1  = indices[1][1]
                        neo_id    = indices[2]
                        thread_id = indices[3]

                        elf_file_indices.ttx.append(kf)
                        elf_file_indices.core_id0s.append(core_id0)
                        elf_file_indices.core_id1s.append(core_id1)
                        elf_file_indices.neo_ids.append(neo_id)
                        elf_file_indices.thread_ids.append(thread_id)

                        elf_files[kf].core[core_id0][core_id1].neo[neo_id].thread[thread_id] = read_elf.get_instruction_profile_from_elf_file(file_name_incl_path, sets = instruction_set, flatten_dict = flatten_dict)

            elf_file_indices.ttx        = sorted(set(elf_file_indices.ttx))
            elf_file_indices.core_id0s  = sorted(set(elf_file_indices.core_id0s))
            elf_file_indices.core_id1s  = sorted(set(elf_file_indices.core_id1s))
            elf_file_indices.neo_ids    = sorted(set(elf_file_indices.neo_ids))
            elf_file_indices.thread_ids = sorted(set(elf_file_indices.thread_ids))

            for ttx_name, core_id0, core_id1, neo_id, thread_id in itertools.product(elf_file_indices.ttx, elf_file_indices.core_id0s, elf_file_indices.core_id1s, elf_file_indices.neo_ids, elf_file_indices.thread_ids):
                # ttx/kernels/core_00_00/neo_0/thread_0/out/thread_0.elf
                elf_file_name = os.path.join(ttx_name, f"core_{core_id0:02d}_{core_id1:02d}", f"neo_{neo_id}", f"thread_{thread_id}", "out", f"thread_{thread_id}.elf")
                elf_file_name_incl_path = os.path.join(ttx_dir, elf_file_name)
                if not os.path.isfile(elf_file_name_incl_path):
                    raise Exception(f"{elf_file_name_incl_path} does not exist!")

    def get_t3sim_test_status(test, path, status):
        import os
        log_file = os.path.join(path, f"{test}.t3sim_test.log")

        status.status = None
        with open(log_file, "r") as file:
            for line in file:
                line = line.strip()
                if line.startswith("Total Cycles"):
                    status.status = "PASS"
                    status.num_cycles = int(line.split("=")[1].strip())  # Extract and store value
                    break

            if not status.status:
                status.status = "FAIL"
                status.num_cycles = line

    instruction_set = get_instruction_set(assembly_yaml)
    status_dict = dict()

    if isinstance(test_names, str):
        test_names = [test_names]

    if isinstance(test_names, (list, tuple, set)):
        for test in test_names:
            status_dict.update({test : test_status()})
            status_dict[test].name = test
            get_rtl_status_of_test(test, root_dir, debug_dir, sim_result_yml, test_dir_suffix, status_dict[test].rtl)
            get_instruction_profile_from_elf_file(test, root_dir, debug_dir, status_dict[test].elf, status_dict[test].elf_file_indices, instruction_set, flatten_dict)
            get_t3sim_test_status(test, t3sim_dir, status_dict[test].pm)
    else:
        msg = f"- error: no method defined to determine the status for test names of type {type(test_names)}"
        raise Exception(msg)

    return status_dict

def check_status(status):
    def check_rtl_test_status(rtl_status):
        if None == test_status.rtl.status:
            print(f"- RTL status for test {test} not known")

        if ("PASS" == test_status.rtl.status) and (not test_status.rtl.num_cycles):
            print(f"- RTL number of cycles for test {test} not known, even though the test status is {test_status.rtl.status}")

    def check_elfs(elf):
        pass

    for test, test_status in status.items():
        check_rtl_test_status(test_status.rtl)

def print_status(status, offset = 2):

    max_test_len = 0
    for test in status.keys():
        max_test_len = max(max_test_len, len(test))

    max_rtl_status_len = 0
    max_rtl_num_cycles = 0
    for test, test_status in status.items():
        max_rtl_status_len = max(max_rtl_status_len, len(test_status.rtl.status))
        max_rtl_num_cycles = max(max_rtl_num_cycles, test_status.rtl.num_cycles)

    max_num_cycles_width = len(str(max_rtl_num_cycles))

    msg  = ""
    for test, test_status in status.items():
        msg += f"{' ' * offset}"
        msg += test + " " * (max_test_len - len(test)) + " "
        msg += test_status.rtl.status + " " * (max_rtl_status_len - len(test_status.rtl.status)) + " "
        msg += f"{test_status.rtl.num_cycles:>{max_num_cycles_width}}" + " "
        msg += f"{test_status.pm.status}  {test_status.pm.num_cycles}"
        msg += "\n"

    print(msg.rstrip())

def write_regression(file_to_read):
    import polars
    print("- reg: file to read: ", file_to_read)
    data = polars.read_csv(file_to_read)
    
    # Group by col2 and count occurrences of P and F in col3
    result = (
        data.group_by("Test class")
        .agg([
            polars.col("PM status").filter(polars.col("PM status") == "PASS").count().cast(polars.Int64).alias("PASS"),
            polars.col("PM status").filter(polars.col("PM status") == "FAIL").count().cast(polars.Int64).alias("FAIL")
        ])
        .with_columns(  # Add total count column
        ((polars.col("PASS") / (polars.col("PASS") + polars.col("FAIL")))).alias("PASS RATE")
    ))

    result = result.sort(result.columns[0], maintain_order=True)

    # Compute the sum of each column and convert to a DataFrame
    totals_row = polars.DataFrame([{
        "Test class" : "Total",  # Label the total row
        "PASS"       : result["PASS"].sum(),
        "FAIL"       : result["FAIL"].sum(),
        "PASS RATE"  : (result["PASS"].sum() / (result["PASS"].sum() + result["FAIL"].sum()))
    }])

    result = polars.concat([result, totals_row])

    result.write_csv(f"regression_{file_to_read}", separator=",")

    print("- Regression: ")
    # polars.Config.set_tbl_cell_numeric_alignment("RIGHT")
    with polars.Config(set_float_precision=2, tbl_rows=len(result), tbl_cell_numeric_alignment="RIGHT"):
        print(result)

def write_failure_types(file_to_read):
    import polars
    data = polars.read_csv(file_to_read)
    result = data.filter(polars.col("Failure type").is_not_null())

    # pivot the table. 
    result = (
        result
        .pivot(values = "Test", index = "Test class", columns = "Failure type", aggregate_function = "count")
        .fill_null(0)
    )

    result = result.sort(result.columns[0], maintain_order=True)

    # Add totals column
    result = result.with_columns(
        polars.sum_horizontal(result.columns[1:]).cast(polars.Int64).alias("Total")  # Correct summing
        )

    # Add total row    
    total_row = polars.DataFrame([{
        "Test class": "Total",
        **{col: result[col].sum() for col in result.columns[1:]}  # Summing each column
    }])

    # Ensure all numeric columns in `pivoted_df` are UInt32 before concatenation
    result = result.with_columns(
        [polars.col(c).cast(polars.Int64) for c in result.columns[1:]]
        )

    result = polars.concat([result, total_row])    

    result.write_csv(f"failure_analysis_{file_to_read}", separator=",")

    print("- Failure analysis")
    # polars.Config.set_tbl_cell_numeric_alignment("RIGHT")
    with polars.Config(set_float_precision=2, tbl_rows=len(result), tbl_cell_numeric_alignment="RIGHT"):
        print(result)

def write_s_curve(file_to_read):
    import polars
    import matplotlib.pyplot as plt

    data = polars.read_csv(file_to_read)
    result = data.filter(polars.col("Perf comparison").is_not_null())
    result = result.select(["Test", "Perf comparison", polars.selectors.starts_with('Number of instructions of kind')]).sort("Perf comparison")

    result.write_csv(f"s_curve_{file_to_read}", separator=",")

    max_col_width = max([len(col) for col in result.columns])
    max_col_width = max(max_col_width, max([len(ele) for ele in list(result.get_column("Test"))]))

    print("S-curve table")
    with polars.Config(set_float_precision=2, tbl_rows=len(result), fmt_str_lengths=max_col_width, tbl_cell_numeric_alignment="RIGHT"):
        print(result)

    # Convert columns to lists for plotting
    x = result["Test"].to_list()  # Categories for x-axis
    y = result["Perf comparison"].to_list()  # Numerical values for y-axis
    num_10pc = len([ele for ele in y if abs(ele - 1.0) <= 0.1])
    num_20pc = len([ele for ele in y if abs(ele - 1.0) <= 0.2])
    num_30pc = len([ele for ele in y if abs(ele - 1.0) <= 0.3])

    # Create the plot
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(x, y, color = "black", linewidth = 1, alpha = 0.5)
    ax.scatter(x, y, )

    # Highlight the region 0.9 to 1.1 slightly darker
    ax.axhspan(0.7, 1.3, color="gray", alpha=0.05, label=f"+/- 30% ({(num_30pc/len(y)):.2f})")

    # Highlight the region 0.9 to 1.1 slightly darker
    ax.axhspan(0.8, 1.2, color="gray", alpha=0.1, label=f"+/- 20% ({(num_20pc/len(y)):.2f})")
    
    # Highlight the region 0.9 to 1.1 slightly darker
    ax.axhspan(0.9, 1.1, color="gray", alpha=0.2, label=f"+/- 10% ({(num_10pc/len(y)):.2f})")

    # Labels and title
    ax.set_xlabel("Tests")
    ax.set_ylabel("Perf comparison (PM/RTL)")
    # ax.set_title("col1 vs col5 Plot")
    ax.tick_params(axis='x', labelrotation=90)

    # Show legend
    ax.legend()

    # Save plot as an SVG file with no extra white space
    plt.savefig(f"s_curve_{file_to_read}.svg", format="svg", bbox_inches="tight")
    plt.savefig(f"s_curve_{file_to_read}.png", format="png", bbox_inches="tight")

    print("- end of s curve")

def write_status_to_csv(status, file_to_write):
    def get_instructions_from_profile(instruction_profile, instructions):
        if all(isinstance(ele, read_elf.instructions.kind) for ele in instruction_profile.keys()):
            for instr_kind, num_instrs in instruction_profile.items():
                if instr_kind not in instructions.keys():
                    instructions.update({instr_kind : set()})

                for instr in num_instrs.keys():
                    instructions[instr_kind].add(instr)

        else:
            for value in instruction_profile.values():
                if isinstance(value, dict):
                    get_instructions_from_profile(value, instructions)

    def get_instructions(status):

        instructions = dict()
        # instructions.update({read_elf.instructions.kind.ttqs : set()})
        # instructions.update({read_elf.instructions.kind.rv32 : set()})
        # todo: write a get_kinds function.

        for test_status in status.values():
            elf_file_indices = test_status.elf_file_indices
            for ttx_name, core_id0, core_id1, neo_id, thread_id in itertools.product(elf_file_indices.ttx, elf_file_indices.core_id0s, elf_file_indices.core_id1s, elf_file_indices.neo_ids, elf_file_indices.thread_ids):
                ip = test_status.elf[ttx_name].core[core_id0][core_id1].neo[neo_id].thread[thread_id]
                get_instructions_from_profile(ip[0], instructions)

        msg = ''
        for kind, instructions_list in instructions.items():
            msg += f"  + Number of instructions of kind {kind}: {len(instructions_list):5d}\n"
            msg += to_matrix_str(sorted(list(instructions_list)), 5, 4).rstrip()
            msg += "\n"


        print(msg.rstrip())

        instruction_list = []
        for kind, instruction_set in instructions.items():
            for instr in instruction_set:
                instruction_list.append(f"{kind}:{instr}")

        return sorted(instruction_list)

    def get_test_class(test):
        classes = {}
        classes['datacopy'.upper()] = {'datacopy'}
        classes['eltw'.upper()]     = {'elwmul', 'elwadd', 'elwsub'}
        classes['matmul'.upper()]   = {'matmul'}
        classes['pck'.upper()]      = {'pck'}
        classes['reduce'.upper()]   = {'reduce'}
        classes['sfpu'.upper()]     = {'lrelu', 'tanh', 'sqrt', 'exp', 'recip', 'relu'} 
        classes['upk'.upper()]      = {'upk'}

        # fields = test.split("-")
        # test_bin = fields[5] if fields[4].startswith("fp") else fields[4]
        # test_class = "SFPU" if test_bin in sfpu_bins else "ELTW" if test_bin in elw_bins else test_bin.upper()

        test_words = test.split("-")

        test_class = None
        for key, values in classes.items():
            for value in values:
                if value in test_words:
                    test_class = key

        if not test_class:
            raise Exception(f"- error: could not determine test class for {test}")
        
        return test_class

    def get_failure_class(test_name, msg):
        bins = {'attribs', 'Too many resources', 'Timeout', 'register', 'KeyboardInterrupt', 'has no attribute', 'Replay', 'Semaphore', "object cannot be interpreted as an integer", "Zero Dst expected", "TypeError: unsupported operand type(s) for &"}
        for b in bins:
            if b in msg:
                return b
            
        raise Exception(f"- error: could not find failure class from message: {msg} for test {test_name}")

    def get_instruction_kinds(status):
        instruction_kinds = set()
        for test_status in status.values():
            instruction_kinds.update(test_status.get_instruction_kinds())

        return instruction_kinds
    
    instructions = get_instructions(status)
    instruction_kinds = get_instruction_kinds(status)

    import csv
    with open(file_to_write, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        header = []
        header.append("Test ID")
        header.append("Test name")
        header.append("TTX directory")
        header.append("core_id0")
        header.append("core_id1")
        header.append("neo_id")
        header.append("thread_id")
        header.append("Function name")
        header.append("RTL status")
        header.append("RTL number of cycles")
        header.append("PM status")
        header.append("PM number of cycles")
        header.extend(instructions)
        writer.writerow(header)
        for test_id, test_name in enumerate(sorted(status.keys())):
            test_status = status[test_name]
            elf_file_indices = test_status.elf_file_indices
            for ttx_name, core_id0, core_id1, neo_id, thread_id in itertools.product(elf_file_indices.ttx, elf_file_indices.core_id0s, elf_file_indices.core_id1s, elf_file_indices.neo_ids, elf_file_indices.thread_ids):
                ip = test_status.elf[ttx_name].core[core_id0][core_id1].neo[neo_id].thread[thread_id]
                functions = sorted(ip[0].keys())
                for function in functions: # assumes flatten_dict is False
                    instruction_profile = ip[0][function]
                    row = []
                    row.append(test_id)
                    row.append(test_status.name)
                    row.append(ttx_name)
                    row.append(core_id0)
                    row.append(core_id1)
                    row.append(neo_id)
                    row.append(thread_id)
                    row.append(function)
                    row.append(test_status.rtl.status)
                    row.append(test_status.rtl.num_cycles)
                    row.append(test_status.pm.status)
                    row.append(test_status.pm.num_cycles)
                    num_instructions = dict()
                    for instr in instructions:
                        num_instructions.update({instr : None})

                    for kind, num_instrs in instruction_profile.items():
                        for mnemonic, num_instr in num_instrs.items():
                            instr = f"{kind}:{mnemonic}"
                            if not instr in num_instructions.keys():
                                raise Exception(f"- error: could not find {instr} in instructions list")

                            num_instructions[instr] = num_instr[0]

                    row.extend(list(num_instructions.values()))
                    writer.writerow(row)

    test_class_dict = dict()
    class_tests_dict = dict()
    for test_name in status.keys():
        test_class = get_test_class(test_name)
        test_class_dict[test_name] = test_class
        if test_class not in class_tests_dict.keys():
            class_tests_dict[test_class] = []
        class_tests_dict[test_class].append(test_name)
    max_test_class_str_len = len(max(class_tests_dict.keys(), key = len))
    max_test_name_str_len = len(max(status.keys(), key = len))
    for tclass in sorted(class_tests_dict.keys()):
        print(f"+ test class: {tclass}")
        for ele in sorted(class_tests_dict[tclass]):
            msg = f"  + {ele:<{max_test_name_str_len}}: RTL: {status[ele].rtl.status}, PM: {status[ele].pm.status}"
            if "FAIL" in (status[ele].pm.status, status[ele].rtl.status):
                print(f"{bcolors.FAIL}{msg}{bcolors.ENDC}")
            else:
                print(msg)

    summary_file_to_write = "summary_" + file_to_write
    with open(summary_file_to_write, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        header = []
        header.append("Test ID")
        header.append("Test class")
        header.append("Test")
        header.append("RTL status")
        header.append("RTL number of cycles")
        header.append("PM status")
        header.append("PM number of cycles")
        header.append("Perf comparison")
        header.append("Failure type")
        for kind in instruction_kinds:
            header.append(f"Number of instructions of kind {kind}")
        
        writer.writerow(header)

        for test_id, test_name in enumerate(sorted(status.keys())):
            test_status = status[test_name]
            row = []
            row.append(test_id)
            row.append(test_class_dict[test_name])
            row.append(test_status.name)
            row.append(test_status.rtl.status)
            row.append(test_status.rtl.num_cycles)
            row.append(test_status.pm.status)
            row.append(test_status.pm.num_cycles)
            if isinstance(test_status.pm.num_cycles, int):
                row.append(test_status.pm.num_cycles / test_status.rtl.num_cycles)
            else:
                row.append(None)

            row.append(None if isinstance(test_status.pm.num_cycles, int) else get_failure_class(test_status.name, test_status.pm.num_cycles))

            num_instructions = test_status.get_num_instructions()
            for kind in instruction_kinds:
                row.append(num_instructions[kind])

            writer.writerow(row)

def get_elf_files(status, root_dir = None, debug_dir = "rsim/debug", test_dir_suffix = "_0", ttx_dir = "ttx"):
    def get_root_dir(root_dir):
        import os
        if None == root_dir:
            root_dir = os.path.dirname(os.path.abspath(__file__))

        if not os.path.exists(root_dir):
            raise Exception(f"- error: given root directory does not exist. given root directory: {root_dir}")

        return root_dir

    root_dir = get_root_dir(root_dir)

    def print_elf_files_for_test(test, root_dir, debug_dir, test_dir_suffix, ttx_dir):
        # import os
        # ttx_dir = os.path.join(root_dir, debug_dir, test + test_dir_suffix, ttx_dir)
        # if not os.path.isdir(ttx_dir):
        #     raise Exception(f"- error: directory {ttx_dir} not found for test {test}")

        # print(f"elf files for test {test}")
        # paths = os.walk(ttx_dir)
        # for pwd, _, file_names in paths:
        #     for file_name in file_names:
        #         if file_name.endswith(".elf"):
        #             print("  ", os.path.join(pwd, file_name))
        # print()

        import os
        ttx_dir = os.path.join(root_dir, debug_dir)

        paths = os.walk(ttx_dir)
        for pwd, _, file_names in paths:
            for file_name in file_names:
                if file_name.endswith(".elf"):
                    print("  ", os.path.join(pwd, file_name))
        print()

    for test, test_status in status.items():
        if "PASS" == test_status.rtl.status:
            print_elf_files_for_test(test, root_dir, debug_dir, test_dir_suffix, ttx_dir)

if "__main__" == __name__:
    pass

