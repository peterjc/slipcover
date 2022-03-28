# Implements an "oracle" to verify slipcover's results by trivial application of
# sys.settrace()

import sys
from pathlib import Path
from slipcover import slipcover as sc
from collections import defaultdict
import dis
import atexit


import argparse
ap = argparse.ArgumentParser(prog='oracle')
ap.add_argument('--out', type=Path, help="specify output file name")
ap.add_argument('--source', help="specify directories to cover")
ap.add_argument('--omit', help="specify file(s) to omit")

g = ap.add_mutually_exclusive_group(required=True)
g.add_argument('-m', dest='module', nargs=1, help="run given module as __main__")
g.add_argument('script', nargs='?', type=Path, help="the script to run")
ap.add_argument('script_or_module_args', nargs=argparse.REMAINDER)

if '-m' in sys.argv: # work around exclusive group not handled properly
    minus_m = sys.argv.index('-m')
    args = ap.parse_args(sys.argv[1:minus_m+2])
    args.script_or_module_args = sys.argv[minus_m+2:]
else:
    args = ap.parse_args(sys.argv[1:])

base_path = Path(args.script).resolve().parent if args.script \
            else Path('.').resolve()

file_matcher = sc.FileMatcher()

if args.source:
    for s in args.source.split(','):
        file_matcher.addSource(s)
elif args.script:
    file_matcher.addSource(Path(args.script).resolve().parent)

if args.omit:
    for o in args.omit.split(','):
        file_matcher.addOmit(o)

coverage = defaultdict(set)

def trace_function(frame, event, arg):
    if not file_matcher.matches(frame.f_code.co_filename):
        return None # uninteresting scope

    if event == 'line':
        coverage[frame.f_code.co_filename].add(frame.f_lineno)

    return trace_function


def get_code_lines(filename):
    with open(filename, 'r') as f:
        code = compile(f.read(), filename, 'exec')
        return set(map(lambda line: line[1], dis.findlinestarts(code)))


def print_coverage(outfile):
    code_lines = {f: get_code_lines(f) for f in coverage}
    data = {'files':
                {f : {'executed_lines': sorted(lines),
                      'missing_lines': sorted(code_lines[f] - lines)}
                     for f, lines in coverage.items()}
    }

    import json
    json.dump(data, outfile, indent=4)
    print("\n", file=outfile)


def oracle_atexit():
    if args.out:
        with open(args.out, "w") as outfile:
            print_coverage(outfile)
    else:
        print_coverage(sys.stdout)

atexit.register(oracle_atexit)
sys.settrace(trace_function)

if args.script:
    # python 'globals' for the script being executed
    script_globals = dict()

    # needed so that the script being invoked behaves like the main one
    script_globals['__name__'] = '__main__'
    script_globals['__file__'] = args.script

    sys.argv = [args.script, *args.script_or_module_args]

    # the 1st item in sys.path is always the main script's directory
    sys.path.pop(0)
    sys.path.insert(0, str(base_path))

    with open(args.script, "r") as f:
        code = compile(f.read(), str(Path(args.script).resolve()), "exec")

    exec(code, script_globals)

else:
    import runpy
    sys.argv = [*args.module, *args.script_or_module_args]
    runpy.run_module(*args.module, run_name='__main__', alter_sys=True)
