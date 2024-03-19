"""Experimental cli helpers."""

import sys
import argparse
import pprint
from . import read_blocks


def parse_args(args):
    parser = argparse.ArgumentParser(prog="rmscene")
    parser.add_argument("file", type=argparse.FileType("rb"), help="filename to read")
    return parser.parse_args(args)


def pprint_file(args) -> None:
    result = read_blocks(args.file)
    for el in result:
        print()
        pprint.pprint(el)


if __name__ == "__main__":
    ARGS = parse_args(sys.argv[1:])
    pprint_file(ARGS)
