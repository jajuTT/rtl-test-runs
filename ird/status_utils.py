#!/usr/bin/env python

import datetime
import os
import rtl_utils
import yaml

def get_rtl_test_status(test, rtl_args):
    key_local_root_dir = "local_root_dir"
    key_local_root_dir_path = "local_root_dir_path"
    key_sim_result_yaml = "sim_result.yaml"
    key_test_dir_suffix = "test_dir_suffix"

    for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
        assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict."

    test_dir = test + rtl_args[key_test_dir_suffix]
    local_root_dir_incl_path = os.path.join(rtl_args[key_local_root_dir_path], rtl_args[key_local_root_dir])
    test_dir_incl_path = rtl_utils.test_names.get_dir_incl_path(local_root_dir_incl_path, test_dir)
    sim_result_incl_path = os.path.join(test_dir_incl_path, rtl_args[key_sim_result_yaml])
    if os.path.isfile(sim_result_incl_path):
        with open(sim_result_incl_path) as stream:
            yml = yaml.safe_load(stream)
            return (True, yml['res'], yml['total-cycles'])
    else:
        return (False, None, None)
    
def get_model_test_status(test, model_args):
    key_model_log_file_suffix = "model_log_file_suffix"
    key_model_root_dir = "model_root_dir"
    key_model_root_dir_path = "model_root_dir_path"
    key_model_odir = "model_odir"

    for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_")]:
        assert key in model_args.keys(), f"- error: {key} not found in given model_args dict."

    model_odir = os.path.join(model_args[key_model_root_dir_path], model_args[key_model_root_dir], model_args[key_model_odir])
    model_log_file_name = test + model_args[key_model_log_file_suffix]
    model_log_file_incl_path = os.path.join(model_odir, model_log_file_name)

    if os.path.isfile(model_log_file_incl_path):
        with open(model_log_file_incl_path, "r") as file:
            for line in file:
                line = line.strip()
                if line.startswith("Total Cycles"):
                    return (True, "PASS", int(round(float(line.split("=")[1].strip()))))

            return (False, "FAIL", line)
    else:
        return (False, None, None)


def get_test_status(test, rtl_args, model_args):
    found_rtl_test, rtl_res, rtl_num_cycles = get_rtl_test_status(test, rtl_args)
    found_model_test, model_res, model_num_cycles = get_model_test_status(test, model_args)

    status = dict()
    status["model"]               = dict()
    status["model"]["found_test"] = found_model_test
    status["model"]["num_cycles"] = model_num_cycles
    status["model"]["result"]     = model_res
    status["rtl"]                 = dict()
    status["rtl"]["found_test"]   = found_rtl_test
    status["rtl"]["num_cycles"]   = rtl_num_cycles
    status["rtl"]["result"]       = rtl_res
    return status

    # if not (isinstance(model_num_cycles, str) and "Too many resources to select from" in model_num_cycles):
    #     print(f"+ test: {test}, RTL: found test: {found_rtl_test}, result: {rtl_res}, num_cycles: {rtl_num_cycles}. Model: found test: {found_model_test}, result: {model_res}, num_cycles: {model_num_cycles}")

def get_tests_status(tests, rtl_args, model_args):
    statuses = dict()
    PASS = "PASS"
    for test in sorted(tests):
        statuses[test] = get_test_status(test, rtl_args, model_args)

    model_errors = dict()
    for key, status in statuses.items():
        num_cycles = status["model"]["num_cycles"]
        if isinstance(num_cycles, str):
            if num_cycles not in model_errors.keys():
                model_errors[num_cycles] = list()
            model_errors[num_cycles].append(key)

    print("\n".join([f"{idx}. {key}, num_tests: {len(model_errors[key])}, tests: {sorted(model_errors[key])}" for idx, key in enumerate(sorted(model_errors.keys()))]))

    perf_nums = dict()
    for key, status in statuses.items():
        found_model = status["model"]["found_test"]
        found_rtl = status["rtl"]["found_test"]
        num_cycles_model = status["model"]["num_cycles"]
        num_cycles_rtl = status["rtl"]["num_cycles"]
        result_model = status["model"]["result"]
        result_rtl = status["rtl"]["result"]
        if found_model and found_rtl and (PASS == result_model) and (PASS == result_rtl):
            if isinstance(num_cycles_model, int) and isinstance(num_cycles_rtl, int):
                perf_nums[key] = num_cycles_model / num_cycles_rtl
            else:
                raise Exception(f"- error: expected num cycles to be int, received: type(num_cycles_rtl): {type(num_cycles_rtl)}, type(num_cycles_model): {type(num_cycles_model)}")
            
    for idx, test in enumerate(sorted(perf_nums.items(), key = lambda x: x[1])):
        print(f"{idx}. {test[0]}: {test[1]}")


def write_status_to_csv(rtl_args, model_args):
    assert isinstance(rtl_args, dict)
    assert isinstance(model_args, dict)

    key_model_odir = "model_odir"
    key_model_root_dir = "model_root_dir"
    key_model_root_dir_path = "model_root_dir_path"
    key_rtl_tag = "rtl_tag"
    
    for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_rtl_")]:
        assert key in rtl_args.keys(), f"- error: {key} not found in given rtl_args dict"
    
    for key in [var_value for var_name, var_value in locals().items() if var_name.startswith("key_model_")]:
        assert key in model_args.keys(), f"- error: {key} not found in given model_args dict"

    csv_file_name = f"status_{rtl_args[key_rtl_tag]}_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv"
    csv_file_path = os.path.join(model_args[key_model_root_dir_path], model_args[key_model_root_dir], model_args[key_model_odir])
    summary_csv_file_name = f"summary_{csv_file_name}"
    csv_file_incl_path = os.path.join(csv_file_path, csv_file_name)
    summary_csv_file_incl_path = os.path.join(csv_file_path, summary_csv_file_name)

    print("+ status will be written to:",         csv_file_incl_path)
    print("+ summary status will be written to:", summary_csv_file_incl_path)

    csv_args = dict()
    status_args["root_dir"]              = os.path.dirname(os.path.abspath(__file__))
    status_args["debug_dir"]             = os.path.join(rtl_args["local_test_bench_dir"], rtl_args["debug_dir"])
    status_args["t3sim_dir"]             = t3sim_args["sim_dir"]
    status_args["sim_result_yml"]        = rtl_args["sim_result_yml"]
    status_args["flatten_dict"]          = False # do not change this.
    status_args["test_dir_suffix"]       = rtl_args["test_dir_suffix"]
    status_args["rtl_log_file_suffix"]   = rtl_args["rtl_log_file_suffix"]
    status_args["t3sim_log_file_suffix"] = t3sim_args["t3sim_log_file_suffix"]
    status_args["assembly_yaml"]         = os.path.join(t3sim_args["sim_dir"], t3sim_args["binutils_dir"], "instruction_sets", t3sim_args["tensix_instructions_kind"], t3sim_args["assembly_yaml"]) # todo: automated instruction sets

    write_status_to_csv(status.get_status(tests, status_args), csv_name)
    # write_regression(summary_csv_name)
    # write_failure_types(summary_csv_name)
    # write_s_curve(summary_csv_name)