#!/usr/bin/env python
import re
import keyword
from enum import Enum
from types import MappingProxyType
from pathlib import Path
from clang.cindex import Index, CursorKind, TokenKind, TypeKind, TranslationUnit

from clang_ast_walker import ClangASTWalker

import argparse
import sys
import os
import glob

regex_numeric = re.compile(
  r"^(0[xX][0-9a-fA-F]+|0[0-7]+|[1-9][0-9]*|0)[uU]{0,2}[lL]{0,2}$",
  re.VERBOSE
)

regex_cpp_define = re.compile(r"^\s*#\s*define\s+[0-9A-Za-z_]+\s+")

def is_oct_dec_hex(s):
  return bool(regex_numeric.match(s.strip()))

parser = argparse.ArgumentParser(add_help = True)
parser.add_argument("--verbose", "-v", action = "store_true",
                    help = "Verbose mode")
parser.add_argument("-I", dest = "include_dirs",
                    action = "append", type = str, default = [],
                    help = "Include directories")
parser.add_argument("-D", dest = "defines",
                    action = "append", type = str, default = [],
                    help = "Preprocessor defines")
parser.add_argument("extras", nargs = 1,
                    help = "Path to the header file")
args = parser.parse_args()

index = Index.create()
header_ast = index.parse(args.extras[0], args = [
  ("-D" + macro) for macro in args.defines
] + [
  ("-I" + dir) for dir in args.include_dirs
], options = (
  0x04 | TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
))

ast_walker = ClangASTWalker().install_ast(header_ast, verbose = args.verbose)
ast_walker.dump_dict()
dic_idfr = ast_walker.get_identifier_dict()
# print(dic_idfr)
# print(dic_idfr.keys())
