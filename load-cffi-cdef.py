#!/usr/bin/env python

import argparse
parser = argparse.ArgumentParser(add_help = True)
parser.add_argument("extras", nargs = 1,
                    help = "Path to the header file")
args = parser.parse_args()

from cffi import FFI
ffi = FFI()
with open(args.extras[0], "r") as fh:
  header_code = fh.read()
ffi.cdef(header_code)
