#!/usr/bin/env python

import datetime
import math
import os
import rtl_utils
import yaml
import copy

def get_test_classes():
    classes = dict()
    classes['datacopy'.upper()] = {'datacopy'}
    classes['eltw'.upper()]     = {'elwmul', 'elwadd', 'elwsub'}
    classes['matmul'.upper()]   = {'matmul'}
    classes['pck'.upper()]      = {'pck'}
    classes['reduce'.upper()]   = {'reduce'}
    classes['sfpu'.upper()]     = {'lrelu', 'tanh', 'sqrt', 'exp', 'recip', 'relu', 'cast'}
    classes['upk'.upper()]      = {'upk'}

    return classes

def get_failure_bins():
    bins = [
        ["attribs expected. Received"], 
        ["IndexError"], 
        ["Timeout", "reached for pipe"], 
        ["Timeout", "reached for valid check"], 
        ["Too many resources to select from"]
    ]

    return bins

def get_failure_bins_as_str():
    str_bins = list()
    for b in get_failure_bins():
        str_bins.append(" ".join([s for s in b]))

    return str_bins

def get_failure_bin_index(msg):
    for idx, b in enumerate(get_failure_bins_as_str()):
        if b == msg:
            return idx
        
    return idx + 1



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
    
def get_failure_bin(msg, test):
    bins = get_failure_bins()

    for strings in bins:
        if len(strings) == sum([1 for s in strings if s in msg]):
            return " ".join([s for s in strings])
        
    raise Exception(f"- error: could not find failure bin for test {test}. msg = {msg}")

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
    PASS = "PASS"
    found_rtl_test, rtl_res, rtl_num_cycles = get_rtl_test_status(test, rtl_args)
    found_model_test, model_res, model_num_cycles = get_model_test_status(test, model_args)
    if (PASS == model_res) and (not isinstance(model_num_cycles, int)):
        raise Exception(f"- error: expected model_num_cycles for test {test} to be of type int as model_res is equal to {PASS}, instead received type(model_num_cycles) = {type(model_num_cycles)}, model_num_cycles = {model_num_cycles}")
    
    status = dict()
    status["model"]               = dict()
    status["model"]["found_test"] = found_model_test
    status["model"]["num_cycles"] = model_num_cycles
    status["model"]["result"]     = model_res
    status["rtl"]                 = dict()
    status["rtl"]["found_test"]   = found_rtl_test
    status["rtl"]["num_cycles"]   = rtl_num_cycles
    status["rtl"]["result"]       = rtl_res
    status["class"]               = get_test_class(test)
    if isinstance(model_num_cycles, str):
        status["failure_bin"] = get_failure_bin(model_num_cycles, test)

    return status

def get_tests_statuses(tests, rtl_args, model_args):
    statuses = dict()
    for test in sorted(tests):
        statuses[test] = get_test_status(test, rtl_args, model_args)

    return statuses

def get_test_class(test):
    classes = get_test_classes()

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

def get_tests_classes(tests):
    tests_classes = dict()
    for test in tests:
        tests_classes[test] = get_test_class(test)

    return tests_classes

def get_classes_tests(tests):
    tests_classes = get_tests_classes(tests)

    classes_tests = dict()
    for c in sorted(tests_classes.values()):
        classes_tests[c] = []

    for test, c in tests_classes.items():
        classes_tests[c].append(test)

    return classes_tests

def get_classes_tests_from_statuses(statuses):
    classes_tests = dict()
    for test, status in statuses.items():
        if status["class"] not in classes_tests.keys():
            classes_tests[status["class"]] = []
        classes_tests[status["class"]].append(test)

    return classes_tests

def get_model_errors_from_statuses(statuses):
    model_errors = dict()
    for key, status in statuses.items():
        num_cycles = status["model"]["num_cycles"]
        if isinstance(num_cycles, str):
            if num_cycles not in model_errors.keys():
                model_errors[num_cycles] = list()
            model_errors[num_cycles].append(key)

    return model_errors
    
def get_model_errors(tests, rtl_args, model_args):
    statuses = get_tests_statuses(tests, rtl_args, model_args)
    return get_model_errors_from_statuses(statuses)

def model_errors_to_str(model_errors):
    errors_msg = ""
    for idx, model_error in enumerate(model_errors.items()):
        msg = model_error[0]
        test_list = model_error[1]
        errors_msg += f"+ {idx}. {len(test_list)} test(s) with error {msg}:\n"
        for test in sorted(test_list):
            errors_msg += f"  + {test}\n"

    return errors_msg.rstrip()

def print_model_errors(model_errors):
    print(model_errors_to_str(model_errors))
    
def get_num_cycles_model_by_rtl_from_statuses(statuses):
    PASS = "PASS"
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
                perf_nums[key] = [num_cycles_model, num_cycles_rtl, float(num_cycles_model) / float(num_cycles_rtl)]
            else:
                raise Exception(f"- error: expected num cycles to be int, received: type(num_cycles_rtl): {type(num_cycles_rtl)}, type(num_cycles_model): {type(num_cycles_model)}")
            
    return perf_nums

def get_num_cycles_model_by_rtl(tests, rtl_args, model_args):
    statuses = get_tests_statuses(tests, rtl_args, model_args)
    return get_num_cycles_model_by_rtl_from_statuses(statuses)

def num_cycles_model_by_rtl_to_str(tests_num_cycles, sort_by = "model_by_rtl"):
    def get_sort_by_index(sort_by):
        sort_by_options = ["model", "rtl", "model_by_rtl"]
        for idx, option in enumerate(sort_by_options):
            if option == sort_by:
                return idx
            
        raise Exception(f"- error: can not determine sort order from given option {sort_by}")
    
    sort_by_idx = get_sort_by_index(sort_by)
    max_test_len = max([len(test) for test in tests_num_cycles.keys()])
    max_idx_len = math.ceil(math.log(len(tests_num_cycles)))
    max_model_num_cycles_len = math.ceil(math.log10(max(num_cycles[0] for num_cycles in tests_num_cycles.values())))
    max_rtl_num_cycles_len = math.ceil(math.log10(max(num_cycles[get_sort_by_index("model")] for num_cycles in tests_num_cycles.values())))
    msg = ""
    for idx, test in enumerate(sorted(tests_num_cycles.items(), key = lambda x: x[1][sort_by_idx])):
        msg += f"{idx:>{max_idx_len}}. {test[0]:<{max_test_len}}: {test[1][0]:>{max_model_num_cycles_len}}, {test[1][1]:>{max_rtl_num_cycles_len}}, {test[1][2]:.2f}\n"

    return msg.rstrip()

def print_num_cycles_model_by_rtl(tests_num_cycles):
    print(num_cycles_model_by_rtl_to_str(tests_num_cycles))

def get_pass_rate_by_class_from_statuses(statuses):
    classes_num_pass = dict()
    classes_tests = get_classes_tests(statuses.keys())
    PASS = "PASS"
    classes_num_pass = dict()
    for c in sorted(classes_tests.keys()):
        num_pass = 0
        for test in classes_tests[c]:
            found_model = statuses[test]["model"]["found_test"]
            found_rtl = statuses[test]["rtl"]["found_test"]
            result_model = statuses[test]["model"]["result"]
            result_rtl = statuses[test]["rtl"]["result"]
            if found_model and found_rtl and (PASS == result_model) and (PASS == result_rtl):
                num_pass += 1

            classes_num_pass[c] = [num_pass, len(classes_tests[c]), float(num_pass) / float(len(classes_tests[c]))]

    return classes_num_pass

def pass_rate_by_class_to_str(pass_rate, sort_by = "class"):
    def get_sort_by_index(sort_by):
        sort_by_options = ["num_pass", "num_tests", "pass_rate"]
        for idx, option in enumerate(sort_by_options):
            if option == sort_by:
                return idx
            
        raise Exception(f"- error: can not determine sort order from given option {sort_by}")
    
    pass_rate = copy.deepcopy(pass_rate)
    
    overall = "Overall"
    assert overall not in pass_rate.keys()
    num_pass = sum([pass_rate[c][0] for c in pass_rate.keys()])
    num_tests = sum([pass_rate[c][1] for c in pass_rate.keys()])
    overall_per_cent = float(num_pass) / float(num_tests)
    pass_rate[overall] = [num_pass, num_tests, overall_per_cent]

    max_len_idx       = math.ceil(math.log10(len(pass_rate)) + 1)
    max_len_class     = max([len(key) for key in pass_rate.keys()])
    max_len_num_pass  = math.ceil(math.log10(max([num_pass[0] for num_pass in pass_rate.values()])))
    max_len_num_tests = math.ceil(math.log10(max([num_pass[1] for num_pass in pass_rate.values()])))

    del pass_rate[overall]
    
    msg = "Pass rate: Class, # PASS, # Tests, %\n"
    if "class" == sort_by:
        for idx, c in enumerate(sorted(pass_rate.keys())):
            per_cent = float(pass_rate[c][0]) / float(pass_rate[c][1])
            msg += f"{idx:>{max_len_idx}}. {c:<{max_len_class}}: {pass_rate[c][0]:>{max_len_num_pass}}, {pass_rate[c][1]:>{max_len_num_tests}}, {per_cent*100.:5.2f}\n"
    else:
        sort_by_idx = get_sort_by_index(sort_by)
        for idx, ele in enumerate(sorted(pass_rate.items(), key = lambda x : x[1][sort_by_idx])):
            c = ele[0]
            per_cent = float(pass_rate[c][0]) / float(pass_rate[c][1])
            msg += f"{idx:>{max_len_idx}}. {c:<{max_len_class}}: {pass_rate[c][0]:>{max_len_num_pass}}, {pass_rate[c][1]:>{max_len_num_tests}}, {per_cent*100.:5.2f}\n"

    msg += f"{(idx + 1):>{max_len_idx}}. {overall:<{max_len_class}}: {num_pass:>{max_len_num_pass}}, {num_tests}, {overall_per_cent*100.:5.2f}\n"
    return msg.rstrip()

def get_failure_bins_from_statuses(statuses):
    bins = [
        ["Too many resources to select from"], 
        ["Timeout", "reached for valid check"], 
        ["Timeout", "reached for pipe"], 
        ["attribs expected. Received"], 
        ["IndexError"]
    ]

    bins_dict = dict()
    for cat in bins:
        key = " ".join([e for e in cat])
        if key in bins_dict.keys():
            raise Exception(f"- error: given key already exists. key: {key}, bins_dict.keys(): {bins_dict.keys()}")
        bins_dict[key] = cat

    fails = dict()
    for c in bins_dict.keys():
        fails[c] = []

    for test, status in statuses:
        # found_model = status["model"]["found_test"]
        # found_rtl = status["rtl"]["found_test"]
        num_cycles_model = status["model"]["num_cycles"]
        # num_cycles_rtl = status["rtl"]["num_cycles"]
        # result_model = status["model"]["result"]
        # result_rtl = status["rtl"]["result"]
        if isinstance(num_cycles_model, str):
            found_cat = False
            for cat, strings in bins_dict.items():
                if len(strings) == sum([1 for s in strings if s in num_cycles_model]):
                    fails[cat].append(test)
                    found_cat = True
                    break

            if not found_cat:
                raise Exception(f"- error: could not bin given test case: {test}, failure message: {num_cycles_model}. categories: {bins_dict.keys()}")

    return fails

def get_pass_rate_and_failure_bins_by_class_from_statuses(statuses):
    classes_tests = get_classes_tests(statuses.keys())
    pass_rate = get_pass_rate_by_class_from_statuses

def print_pass_rate_by_class(pass_rate, sort_by = "class"):
    print(pass_rate_by_class_to_str(pass_rate, sort_by))

def overall_status_to_str(statuses):
    PASS = "PASS"
    num_tests = len(statuses)
    num_pass_rtl = 0
    num_pass_model = 0
    for test, status in statuses.items():
        if "failure_bin" not in status.keys():
            num_pass_model += 1
        if PASS == status["rtl"]["result"]:
            num_pass_rtl += 1

    msg = f"Number of tests: {num_tests}, Pass rate:  RTL: {((num_pass_rtl / num_tests) * 100.):5.2f} %, Model: {((num_pass_model / num_tests) * 100.):5.2f} % ({num_tests - num_pass_model} failures)"

    return msg

def print_overall_status(statuses):
    print(overall_status_to_str(statuses))

def get_status_for_class(test_class, statuses):
    num_pass = 0
    num_tests = 0
    num_fail = [0 for _ in get_failure_bins_as_str()]
    tests = list()
    for test, status in statuses.items():
        if test_class == status["class"]:
            tests.append(test)
            num_tests += 1
            if "failure_bin" not in status.keys():
                num_pass += 1
            else:
                num_fail[get_failure_bin_index(status["failure_bin"])] += 1

    class_status = dict()
    class_status["tests"] = tests
    assert num_tests == len(class_status["tests"])
    class_status["num_pass"] = num_pass
    class_status["num_fail"] = num_fail
    assert (num_pass + sum(num_fail)) == num_tests

    return class_status

def get_status_by_class(statuses):
    classes_statuses = dict()
    for c in get_test_classes():
        classes_statuses[c] = get_status_for_class(c, statuses)

    return classes_statuses

def status_by_class_to_str(statuses): # classes_statuses
    overall = "Overall"
    assert overall not in statuses.keys()

    failure_bins_as_str = get_failure_bins_as_str()
    status_dict = dict()
    status_dict["tests"] = []
    status_dict["num_pass"] = 0
    status_dict["num_fail"] = [0 for _ in failure_bins_as_str]
    for status in statuses.values():
        status_dict["tests"].extend(status["tests"])
        status_dict["num_pass"] += status["num_pass"]
        for idx in range(len(status_dict["num_fail"])):
            status_dict["num_fail"][idx] += status["num_fail"][idx]

    assert len(status_dict["tests"]) == sum(len(status["tests"]) for status in statuses.values())
    assert status_dict["num_pass"] == sum(status["num_pass"] for status in statuses.values())
    for idx in range(len(status_dict["num_fail"])):
        assert status_dict["num_fail"][idx] == sum(status["num_fail"][idx] for status in statuses.values())
    assert status_dict["num_pass"] + sum(status_dict["num_fail"]) == len(status_dict["tests"])
    
    statuses[overall] = status_dict

    max_idx_len       = math.ceil(math.log10(len(statuses)))
    max_class_len     = max([len(key) for key in statuses.keys()])
    max_num_tests_len = math.ceil(math.log10(max([len(status["tests"]) for status in statuses.values()])))
    max_num_pass_len  = math.ceil(math.log10(max([status["num_pass"] for status in statuses.values()])))
    max_num_fails_len = math.ceil(math.log10(max([sum(status["num_fail"]) for status in statuses.values()])))
    max_num_fail_len  = [sum([status["num_fail"][idx] for status in statuses.values()]) for idx in range(len(failure_bins_as_str))]
    max_bin_str_len   = max([len(key) for key in failure_bins_as_str])

    # del statuses[overall]

    msg = ""
    for idx, test_class in enumerate(statuses.keys()):
        status = statuses[test_class]
        per_cent_pass = status["num_pass"]/len(status["tests"]) * 100.
        per_cent_fails = sum(status["num_fail"])/len(status["tests"]) * 100.
        msg += f"{idx:>{max_idx_len}}. {test_class:<{max_class_len}}: Num tests: {len(status["tests"]):>{max_num_tests_len}}, Num pass: {status["num_pass"]:>{max_num_pass_len}} ({per_cent_pass:6.2f} %), Num fails: {sum(status["num_fail"]):>{max_num_fails_len}} ({per_cent_fails:6.2f} %)\n"
        msg += "  - failure bins:\n"
        for fidx in range(len(status["num_fail"])):
            msg += f"    - {failure_bins_as_str[fidx]:<{max_bin_str_len}}: {status['num_fail'][fidx]:>{max_num_fails_len}}\n"

    return msg
        

def print_status(tests, rtl_args, model_args, sort_pass_rate_by = "class"):
    statuses = get_tests_statuses(tests, rtl_args, model_args)
    print(f"+ Overall status: {overall_status_to_str(statuses)}")
    print()
    print("+ Status by test class")
    print(status_by_class_to_str(get_status_by_class(statuses)))
    print()
    print("+Number of cycles: Test, Model, RTL, model/rtl")
    print_num_cycles_model_by_rtl(get_num_cycles_model_by_rtl_from_statuses(statuses))


    

    # model_errors = get_model_errors_from_statuses(statuses)
    # num_cycles = get_num_cycles_model_by_rtl_from_statuses(statuses)
    # pass_rate = get_pass_rate_by_class_from_statuses(statuses)
    # print("Model errors")
    # print_model_errors(model_errors)
    # print()
    # print("Number of cycles: Test, Model, RTL, model/rtl")
    # print_num_cycles_model_by_rtl(num_cycles)
    # print()
    # print("Pass rate by class")
    # print_pass_rate_by_class(pass_rate, sort_pass_rate_by)

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