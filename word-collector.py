#!/usr/bin/env python

import sys
import argparse
from pathlib import Path
from clang.cindex import Index, TranslationUnit

parser = argparse.ArgumentParser(add_help = True)
parser.add_argument("--verbose", "-v", action = "store_true",
                    help = "verbose mode")
parser.add_argument("-I", dest = "include_dirs",
                    action = "append", type = str, default = [],
                    help = "Include directories")
parser.add_argument("-D", dest = "defines",
                    action = "append", type = str, default = [],
                    help = "Preprocessor defines")
parser.add_argument("--debug", action = "store_true",
                    help = "Debug")
parser.add_argument("--selection", type = str, default = "MINIMUM",
                    help = "Mode of field/type modification: {ALWAYS|MINIMUM|LIST|HYBRID}")
parser.add_argument("--modify-names-in", type = str, default = None,
                    help = "Pathname of the list of the names to be modified")
parser.add_argument("--modifier-prefix", type = str, default = "",
                    help = "String to insert before the words to be modified")
parser.add_argument("--modifier-suffix", type = str, default = "_",
                    help = "String to append after the words to be modified")
parser.add_argument("--kinds-modify", type = str, default = "field,enum_constant,macro_definition",
                    help = "CSV-string to select the declarations to modify "
                           "(default = field,enum_constant,macro_definition)")
parser.add_argument("extras", nargs = 1,
                    help = "Path to the header file")
args = parser.parse_args()

target_header = Path(args.extras[0]).resolve()
include_dirs = [Path(d).resolve() for d in args.include_dirs]

from ast_name_collector import ASTNameCollector
name_collector = ASTNameCollector()
name_collector.set_debug(args.debug)
name_collector.set_emitter_kinds_by_csv(args.kinds_modify)
name_collector.modifier.prefix = args.modifier_prefix
name_collector.modifier.suffix = args.modifier_suffix
name_collector.modifier.set_selection_by_str(args.selection, args.modify_names_in)
name_collector.cpp.target_source = args.extras[0]
name_collector.cpp.defines = args.defines
name_collector.cpp.include_dirs = args.include_dirs
index = Index.create()
header_ast = index.parse(args.extras[0], args = [
  ("-D" + macro) for macro in args.defines
] + [
  ("-I" + dir) for dir in args.include_dirs
], options = TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)

substitution_graph = name_collector.get_substitution_graph(header_ast)

for emitter_cursor, adic in substitution_graph.items():
  print(f"{adic.location_str} {adic.spelling_old} -> {adic.spelling}")
