#!/usr/bin/env python
import re
import keyword
from enum import Enum
from pathlib import Path
from clang.cindex import Index, CursorKind, TokenKind, TypeKind, TranslationUnit

from attrdict import AttrDict

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
                    help = "verbose mode")
parser.add_argument("-I", dest = "include_dirs",
                    action = "append", type = str, default = [],
                    help = "Include directories")
parser.add_argument("-D", dest = "defines",
                    action = "append", type = str, default = [],
                    help = "Preprocessor defines")
parser.add_argument("extras", nargs = 1,
                    help = "Path to the header file")
args = parser.parse_args()

dic_pls = dict()
dic_token_identifier = dict()

def append_file_to_dict_pls(path):
  dic_pls[path] = dict()

  with open(path, "r") as fh:
    lines = fh.read().splitlines()

  for i, str in enumerate(lines, start = 1):
    dic_pls[path][i] = str

def update_dict_path_line_string(ast):
  for h in ast.get_includes():
    append_file_to_dict_pls(h.include.name)

def get_string_from_path_line(path, line):
  if path in dic_pls and line in dic_pls[path]:
    return dic_pls[path][line]
  return None

def extents_overlap(x1, x2):
  if x1.start.file is None or x2.start.file is None:
    return False # we cannot evaluate
  if x1.start.file.name != x2.start.file.name:
    return False
  if x1.end.line < x2.start.line:
    return False
  if x2.end.line < x1.start.line:
    return False
  if x1.start.line < x2.start.line and x2.start.line < x1.end.line:
    return True
  if x2.start.line < x1.start.line and x1.start.line < x2.end.line:
    return True
  if x1.start.line == x2.start.line and x1.start.line == x1.end.line and x1.end.line == x2.end.line:
    if (x1.start.column - x2.start.column) * (x1.end.column - x2.end.column) > 0:
      return False
    else:
      return True
  else:
    return False

def get_string_from_extent(extent):
  if extent.start.file is None or extent.start.file.name is None:
    return "<extent.start.file is None>"

  s0 = get_string_from_path_line(extent.start.file.name, extent.start.line)
  if s0 is None:
    return f"<cannot get string for {extent.start.file.name}:{extent.start.line}>"
  elif extent.start.line == extent.end.line:
    return s0[(extent.start.column - 1):(extent.end.column - 1)]
  else:
    s1 = get_string_from_path_line(extent.end.file.name, extent.end.line)
    return " ... ".join([
      s0[(extent.start.column - 1):],
      s1[:(extent.end.column - 1)].split()[-1]
    ])

def extent_as_string(extent, full_path = True):
  if extent.start.file is None:
    b = "<NONE>"
  elif full_path:
    b = extent.start.file.name
  else:
    b = Path(extent.start.file.name).name

  if extent.start.line != extent.end.line:
    return (
      f"{b}:{extent.start.line}:{extent.start.column}.."
      f"{extent.end.line}:{extent.end.column}"
    )
  else:
    return (
      f"{b}:{extent.start.line}:"
      f"{extent.start.column}..{extent.end.column}"
    )

def dump_tokens(cursor, indent):
  for t in cursor.translation_unit.get_tokens(extent = cursor.extent):
    token_line_first = t.spelling.split()[0]
    print(f"{indent}  {t.kind} {token_line_first}")
    if t.kind == TokenKind.IDENTIFIER and t.extent.start.file is not None:
      tspl = t.spelling
      if tspl not in dic_token_identifier:
        dic_token_identifier[tspl] = AttrDict()
        dic_token_identifier[tspl].cursors = []
        dic_token_identifier[tspl].tokens = []
      sx = extent_as_string(t.extent)
      if not any(extent_as_string(t.extent) == sx for t in dic_token_identifier[tspl].tokens):
        dic_token_identifier[tspl].cursors.append(cursor)
        dic_token_identifier[tspl].tokens.append(t)
  print("")

def walk(cursor, indent):
  # print(f"{indent}{str(cursor.kind)} \'{get_string_from_extent(cursor.extent)}\'")
  print(f"{indent}{str(cursor.kind)} \'{cursor.spelling}\' in "
        f"\'{get_string_from_extent(cursor.extent)}\'")
        # f"\'{extent_as_string(cursor.extent, False)}\'")
  child_cursors = list(cursor.get_children())
  dump_tokens(cursor, indent)
  #if len(child_cursors) == 0:
  #  dump_tokens(cursor, indent)

  for c in child_cursors:
    walk(c, indent + "    ")

index = Index.create()
header_ast = index.parse(args.extras[0], args = [
  ("-D" + macro) for macro in args.defines
] + [
  ("-I" + dir) for dir in args.include_dirs
], options = (
  0x04 | TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
))

update_dict_path_line_string(header_ast)
# print(dic_pls)
walk(header_ast.cursor, "")

# for idfr, ad in dic_token_identifier.items():
for idfr in sorted(dic_token_identifier.keys()):
  print(idfr)
  ad = dic_token_identifier[idfr]
  for c, t in zip(ad.cursors, ad.tokens):
    ck = c.kind
    x = t.extent
    sx = extent_as_string(x, False)
    l = get_string_from_path_line(x.start.file.name, x.start.line)
    print(f"  {ck} {sx} {l}")
