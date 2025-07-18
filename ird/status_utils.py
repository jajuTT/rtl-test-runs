#!/usr/bin/env python

import copy
import datetime
import math
import matplotlib.pyplot as plt
import os
import rtl_utils
import yaml

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

    return sorted(bins)

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

def get_test_class(test):
    classes = get_test_classes()

    test_words = test.split("-")

    test_class = None
    for key, values in classes.items():
        for value in values:
            if value in test_words:
                test_class = key

    if not test_class:
        raise Exception(f"- error: could not determine test class for {test}")

    return test_class

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

def get_test_class_wise_num_cycles_model_by_rtl_from_statuses(statuses):
    PASS = "PASS"
    perf_nums = dict()
    for test in sorted(statuses.keys()):
        status = statuses[test]
        found_model = status["model"]["found_test"]
        found_rtl = status["rtl"]["found_test"]
        num_cycles_model = status["model"]["num_cycles"]
        num_cycles_rtl = status["rtl"]["num_cycles"]
        result_model = status["model"]["result"]
        result_rtl = status["rtl"]["result"]
        test_class = status["class"]
        if found_model and found_rtl and (PASS == result_model) and (PASS == result_rtl):
            if test_class not in perf_nums.keys():
                perf_nums[test_class] = dict()
            perf_nums[test_class][test] = [num_cycles_model, num_cycles_rtl, float(num_cycles_model)/float(num_cycles_rtl)]

    sorted_perf_nums = dict()
    for key in sorted(perf_nums.keys()):
        value = perf_nums[key]
        sorted_perf_nums[key] = {value_key : value[value_key] for value_key in sorted(value.keys())}

    return sorted_perf_nums

def get_sort_by_index_for_num_cycles_model_by_rtl(sort_by):
    sort_by_options = ["model", "rtl", "model_by_rtl"]
    for idx, option in enumerate(sort_by_options):
        if option == sort_by:
            return idx

    raise Exception(f"- error: can not determine sort order from given option {sort_by}")

def test_class_wise_num_cycles_model_by_rtl_to_str(perf_nums, sort_by = "model_by_rtl"):
    sort_by_idx = get_sort_by_index_for_num_cycles_model_by_rtl(sort_by)
    max_test_len = max([max(len(key) for key in perf_nums[test_class].keys()) for test_class in perf_nums.keys()])
    max_idx_len = math.ceil(math.log(max([len(value) for key, value in perf_nums.items()])))
    max_model_num_cycles_len = math.ceil(math.log10(max([max(value[get_sort_by_index_for_num_cycles_model_by_rtl("model")] for value in perf_nums[test_class].values()) for test_class in perf_nums.keys()])))
    max_rtl_num_cycles_len = math.ceil(math.log10(max([max(value[get_sort_by_index_for_num_cycles_model_by_rtl("rtl")] for value in perf_nums[test_class].values()) for test_class in perf_nums.keys()])))
    msg = ""
    for test_class in sorted(perf_nums.keys()):
        msg += f"+ Test class: {test_class}\n"
        tests_num_cycles = perf_nums[test_class]
        if 0 != len(tests_num_cycles):
            for idx, test_num_cycles in enumerate(sorted(tests_num_cycles.items(), key = lambda x: x[1][sort_by_idx])):
                test = test_num_cycles[0]
                num_cycles = test_num_cycles[1]
                msg += f"  {idx:>{max_idx_len}}. {test:<{max_test_len}}: {num_cycles[0]:>{max_model_num_cycles_len}}, {num_cycles[1]:>{max_rtl_num_cycles_len}}, {num_cycles[2]:.2f}\n"

    return msg.rstrip()

def get_num_cycles_model_by_rtl(tests, rtl_args, model_args):
    statuses = get_tests_statuses(tests, rtl_args, model_args)
    return get_num_cycles_model_by_rtl_from_statuses(statuses)

def num_cycles_model_by_rtl_to_str(tests_num_cycles, sort_by = "model_by_rtl"):
    sort_by_idx = get_sort_by_index_for_num_cycles_model_by_rtl(sort_by)
    max_test_len = max([len(test) for test in tests_num_cycles.keys()])
    max_idx_len = math.ceil(math.log(len(tests_num_cycles)))
    max_model_num_cycles_len = math.ceil(math.log10(max(num_cycles[get_sort_by_index_for_num_cycles_model_by_rtl("model")] for num_cycles in tests_num_cycles.values())))
    max_rtl_num_cycles_len = math.ceil(math.log10(max(num_cycles[get_sort_by_index_for_num_cycles_model_by_rtl("rtl")] for num_cycles in tests_num_cycles.values())))
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

def get_status_for_class(test_class, statuses):
    PASS = "PASS"
    key_tests = "tests"
    bins = get_failure_bins_as_str()
    assert PASS not in bins
    assert key_tests not in bins
    bins.append(PASS)
    bins.append(key_tests)
    bins = sorted(bins)

    num_pass = 0
    num_tests = 0
    num_fail = [0 for _ in get_failure_bins_as_str()]
    test_bins = dict()
    for b in bins:
        test_bins[b] = []

    for test, status in statuses.items():
        if test_class == status["class"]:
            test_bins[key_tests].append(test)
            num_tests += 1
            if "failure_bin" not in status.keys():
                num_pass += 1
                test_bins[PASS].append(test)
            else:
                num_fail[get_failure_bin_index(status["failure_bin"])] += 1
                assert status["failure_bin"] in test_bins.keys()
                test_bins[status["failure_bin"]].append(test)

    for key, value in test_bins.items():
        test_bins[key] = sorted(value)

    assert num_tests == len(test_bins[key_tests])
    assert num_pass == len(test_bins[PASS])
    for bin in get_failure_bins_as_str():
        bin_idx = get_failure_bin_index(bin)
        assert len(test_bins[bin]) == num_fail[bin_idx]

    assert len(test_bins[key_tests]) == sum(len(value) for key, value in test_bins.items() if key != key_tests)

    return test_bins

def get_status_by_class(statuses):
    classes_statuses = dict()
    for c in sorted(get_test_classes()):
        classes_statuses[c] = get_status_for_class(c, statuses)

    return classes_statuses

def status_by_class_to_str(statuses): # classes_statuses
    overall = "Overall"
    assert overall not in statuses.keys()

    key_tests = "tests"
    PASS = "PASS"

    failure_bins_as_str = get_failure_bins_as_str()
    status_dict = dict()
    for status in statuses.values():
        for key in status.keys():
            status_dict[key] = []
        break

    for status in statuses.values():
        for key, value in status.items():
            status_dict[key].extend(value)

    for key, value in status_dict.items():
        status_dict[key] = sorted(value)

    assert key_tests in status_dict.keys()
    assert len(status_dict[key_tests]) == sum(len(status_dict[key]) for key in status_dict.keys() if key != key_tests)
    assert (2 * len(status_dict[key_tests])) == sum(len(status_dict[key]) for key in status_dict.keys()) # same as above

    for key, value in status_dict.items():
        assert len(value) == sum(len(status[key]) for status in statuses.values())

    statuses = copy.deepcopy(statuses)
    statuses[overall] = status_dict

    failure_bins_as_str = sorted(get_failure_bins_as_str())
    max_idx_len         = math.ceil(math.log10(len(statuses)))
    max_class_len       = max([len(key) for key in statuses.keys()])
    max_num_tests_len   = math.ceil(math.log10(max([len(status[key_tests]) for status in statuses.values()])))
    max_num_pass_len    = math.ceil(math.log10(max([len(status[PASS]) for status in statuses.values()])))
    max_num_fails_len   = math.ceil(math.log10(max([sum(len(status[key]) for key in failure_bins_as_str) for status in statuses.values()])))
    max_bin_str_len     = max([len(key) for key in failure_bins_as_str])

    # del statuses[overall]

    msg = ""
    for idx, test_class in enumerate(statuses.keys()):
        status = statuses[test_class]
        num_tests      = len(status[key_tests])
        num_pass       = len(status[PASS])
        num_fails      = [len(status[key]) for key in failure_bins_as_str]
        per_cent_pass  = num_pass/num_tests * 100.
        per_cent_fails = sum(num_fails)/num_tests * 100.
        msg += f"{idx:>{max_idx_len}}. {test_class:<{max_class_len}}: Num tests: {num_tests:>{max_num_tests_len}}, Num pass: {num_pass:>{max_num_pass_len}} ({per_cent_pass:6.2f} %), Num fails: {sum(num_fails):>{max_num_fails_len}} ({per_cent_fails:6.2f} %)\n"
        msg += "  - failure bins:\n"
        for bin in failure_bins_as_str:
            msg += f"    - {bin:<{max_bin_str_len}}: {len(status[bin]):>{max_num_fails_len}}\n"

    return msg

def failed_tests_by_test_class_to_str(statuses): # classes_statuses
    failure_bin_as_str = sorted(get_failure_bins_as_str())
    max_idx_len = math.ceil(math.log10(max(len(status[bin]) for status in statuses.values() for bin in failure_bin_as_str)))
    msg = ""
    for c, status in statuses.items():
        msg += f"+ Test class: {c}\n"
        for bin in failure_bin_as_str:
            if 0 != len(status[bin]):
                msg += f"  + bin: {bin}\n"
                for idx, test in enumerate(sorted(status[bin])):
                    msg += f"    {idx:>{max_idx_len}}. {test}\n"

    return msg.rstrip()

def print_status(tests, rtl_args, model_args, sort_pass_rate_by = "class"):
    statuses = get_tests_statuses(tests, rtl_args, model_args)
    classes_statuses = get_status_by_class(statuses)
    print(f"+ Overall status: {overall_status_to_str(statuses)}")
    print()
    print("+ Status by test class")
    print(status_by_class_to_str(classes_statuses))
    print()
    print("+ Number of cycles: Test, Model, RTL, model/rtl")
    print_num_cycles_model_by_rtl(get_num_cycles_model_by_rtl_from_statuses(statuses))
    print()
    print("+ Test class wise number of cycles. Test, model, RTL, model/rtl")
    print(test_class_wise_num_cycles_model_by_rtl_to_str(get_test_class_wise_num_cycles_model_by_rtl_from_statuses(statuses)))
    print()
    print("+ Failed tests by test class")
    print(failed_tests_by_test_class_to_str(classes_statuses))

def plot_s_curve(tests_num_cycles, file_to_write = ""):
    sort_by_idx = get_sort_by_index_for_num_cycles_model_by_rtl("model_by_rtl")
    x = [None for _ in range(len(tests_num_cycles))]
    y = [None for _ in range(len(tests_num_cycles))]
    for idx, elem in enumerate(sorted(tests_num_cycles.items(), key = lambda x: x[1][sort_by_idx])):
        test = elem[0]
        num_cycles = elem[1]
        x[idx] = test
        y[idx] = num_cycles[sort_by_idx]

    assert all(ele is not None for ele in x)
    assert all(ele is not None for ele in y)
    assert len(x) == len(y)

    num_tests = len(x)
    num_tests_len = math.ceil(math.log10(num_tests))

    x = [f"{x[idx]} ({y[idx]:.2f})" for idx in range(len(x))]

    num_10pc = len([ele for ele in y if abs(ele - 1.0) <= 0.1])
    num_20pc = len([ele for ele in y if abs(ele - 1.0) <= 0.2])
    num_30pc = len([ele for ele in y if abs(ele - 1.0) <= 0.3])

    fig, ax = plt.subplots(figsize=(8, 4))
    # ax.plot(x, y, color = "black", linewidth = 1, alpha = 0.5)
    # ax.scatter(x, y, alpha = 0.5)
    ax.axhline(1, color = 'black', linestyle = "--", linewidth = 0.5, alpha = 0.5, label = f"{sum([1 for ele in y if ele <= 1])} tests with PM/RTL <= 1")
    ax.plot(x, y,
            color     = [0,0,0],
            marker    = 'o',
            linestyle = '-',
            linewidth = 1.0,
            alpha     = 1,
            markerfacecolor = [1,1,1],
            # markeredgecolor = colors[test_class_idx],
            markevery = 1)

    # Highlight the region 0.9 to 1.1 slightly darker
    ax.axhspan(0.7, 1.3, color="gray", alpha=0.05, label=f"+/- 30% ({num_30pc}/{num_tests} tests, {((num_30pc/num_tests)*100):.0f}%)")

    # Highlight the region 0.9 to 1.1 slightly darker
    ax.axhspan(0.8, 1.2, color="gray", alpha=0.1,  label=f"+/- 20% ({num_20pc}/{num_tests} tests, {((num_20pc/num_tests)*100):.0f}%)")

    # Highlight the region 0.9 to 1.1 slightly darker
    ax.axhspan(0.9, 1.1, color="gray", alpha=0.2,  label=f"+/- 10% ({num_10pc}/{num_tests} tests, {((num_10pc/num_tests)*100):.0f}%)")

    # Labels and title
    ax.set_xlabel("Tests")
    ax.set_ylabel("Perf comparison (PM/RTL)")
    # ax.set_title("col1 vs col5 Plot")
    ax.tick_params(axis='x', labelrotation=90, labelsize = 6)

    # Show legend
    ax.legend()

    # Save plot as an SVG file with no extra white space
    plt.savefig(f"s_curve_{file_to_write}.svg", format="svg", bbox_inches="tight", dpi = 512)
    plt.savefig(f"s_curve_{file_to_write}.png", format="png", bbox_inches="tight", dpi = 512)

    print("- end of s curve")

def plot_test_class_wise_s_curve(tests, rtl_args, model_args, file_to_write):
    sort_by = "model_by_rtl"
    num_markers_per_line = 5
    statuses = get_tests_statuses(tests, rtl_args, model_args)
    perf_nums = get_test_class_wise_num_cycles_model_by_rtl_from_statuses(statuses)
    sort_by_idx = get_sort_by_index_for_num_cycles_model_by_rtl(sort_by)
    x_dict = dict()
    x_labels = dict()
    idx_x = 1
    maxy = -1
    for test_class in sorted(perf_nums.keys()):
        tests_num_cycles = perf_nums[test_class]
        if 0 != len(tests_num_cycles):
            for test_num_cycles in sorted(tests_num_cycles.items(), key = lambda x: x[1][sort_by_idx]):
                test = test_num_cycles[0]
                maxy = max(maxy, test_num_cycles[1][sort_by_idx])
                x_dict[test] = idx_x
                idx_x += 1
    miny = maxy
    for test_class in perf_nums.keys():
        tests_num_cycles = perf_nums[test_class]
        for test_num_cycles in tests_num_cycles.values():
            miny = min(miny, test_num_cycles[sort_by_idx])

    # Get colors from the default color cycle
    colors = plt.rcParams['axes.prop_cycle'].by_key()['color']
    assert len(colors) >= len(perf_nums)

    fig, ax = plt.subplots(figsize=(12, 4))

    for test_class_idx, test_class in enumerate(sorted(perf_nums.keys())):
        tests_num_cycles = perf_nums[test_class]
        tests = []
        for test_num_cycles in sorted(tests_num_cycles.items(), key = lambda x: x[1][sort_by_idx]):
            test = test_num_cycles[0]
            tests.append(test)

        x = [x_dict[test] for test in tests]
        y = [tests_num_cycles[test][sort_by_idx] for test in tests]
        for idx, test in enumerate(tests):
            x_labels[test] = f"{test} ({y[idx]:.2f})"
        ax.plot(x, y, color = "black", linewidth = 1, alpha = 0.5)
        # ax.scatter(x, y, alpha = 0.5)
        mark_every = max(1, int(round(len(x) / num_markers_per_line)))
        ax.plot(x, y,
            color     = [0,0,0],
            marker    = 'o',
            linestyle = '-',
            linewidth = 1.0,
            alpha     = 1,
            markerfacecolor = colors[test_class_idx],
            # markeredgecolor = colors[test_class_idx],
            markevery = mark_every)

        ax.axvspan(min(x) - 0.5, max(x) + 0.5, color = colors[test_class_idx], alpha=0.05)
        y_for_text = maxy - (maxy - miny) * 0.07 if len(x) > 3 else maxy
        ax.text(min(x), y_for_text, test_class, color = colors[test_class_idx])

    # Labels and title
    ax.set_xlabel("Tests")
    ax.set_ylabel("Perf comparison (PM/RTL)")
    # ax.set_title("col1 vs col5 Plot")
    ax.set_xticks(list(x_dict.values()))
    ax.set_xticklabels(list(x_labels.values()))
    ax.tick_params(axis='x', labelrotation=90, labelsize = 6)

    plt.savefig(f"test_class_wise_s_curve_{file_to_write}.svg", format="svg", bbox_inches="tight", dpi = 512)
    plt.savefig(f"test_class_wise_s_curve_{file_to_write}.png", format="png", bbox_inches="tight", dpi = 512)





def write_status_to_csv(rtl_args, model_args):
    pass