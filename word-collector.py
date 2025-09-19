#!/usr/bin/env python

import argparse
import sys
import re
import os
import glob
from pathlib import Path
from clang.cindex import Index, CursorKind, TypeKind, TranslationUnit

producer_kinds = {
  CursorKind.STRUCT_DECL,
  CursorKind.UNION_DECL,
  CursorKind.ENUM_DECL,
  CursorKind.ENUM_CONSTANT_DECL,
  CursorKind.TYPEDEF_DECL,
  CursorKind.FUNCTION_DECL,
  CursorKind.VAR_DECL,
  CursorKind.FIELD_DECL,

  CursorKind.MACRO_DEFINITION,
}

consumer_kinds = {
  CursorKind.TYPE_REF,
  CursorKind.DECL_REF_EXPR,
  CursorKind.MEMBER_REF_EXPR,
  CursorKind.CALL_EXPR,
  CursorKind.UNEXPOSED_EXPR,

  CursorKind.MACRO_INSTANTIATION,
}

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
#parser.add_argument("--word-modification", type = str, default = "NONE",
#                    help = "Mode of field/type modification: {ALWAYS|MINIMUM|LIST|HYBRID}")
#parser.add_argument("--modify-words-in", type = str, default = None,
#                    help = "Pathname of the list of the words to be modified")
#parser.add_argument("--modifier-prefix", type = str, default = "",
#                    help = "String to insert before the words to be modified")
#parser.add_argument("--modifier-suffix", type = str, default = "_",
#                    help = "String to append after the words to be modified")
parser.add_argument("extras", nargs = 1,
                    help = "Path to the header file")
args = parser.parse_args()

target_header = Path(args.extras[0]).resolve()
include_dirs = [Path(d).resolve() for d in args.include_dirs]

words_provided = set([])
words_referred = set([])

#args.word_modification = args.word_modification.upper()
#if args.modify_words_in is not None and args.word_modification == "LIST":
#  with open(args.modify_words_in, "r") as fh:
#    args.modify_words_in = set([])
#    for _line in fh.read().split("\n"):
#      _toks = re.split(r"[^0-9A-Za-z_]", _line)
#      if len(_toks) > 0:
#        args.modify_words_in.add(_toks[0])
#
#if args.word_modification in {"MINIMUM", "HYBRID"}:
#  import keyword
#  if args.modify_words_in is None:
#    args.modify_words_in = set([])
#  args.modify_words_in.update(keywords.kwlist)
#
#def modify_word(word_original):
#  if args.word_modification == "NONE":
#    return word_original
#  elif args.word_modification == "ALWAYS" or word_original in args.modify_words_in:
#    return args.modifier_prefix + word_original + args.modifier_suffix

user_macros = [d.split("=", 1)[0].strip() for d in args.defines]

class AttrDict:
  def __init__(self, d = None):
    self._data = dict(d) if d is not None else {}

  def __getattr__(self, k):
    return self._data.get(k, None)

  def __setattr__(self, k, v):
    if k == "_data":
      super().__setattr__(k, v)
    else:
      self._data[k] = v

  def keys(self):
    return self._data.keys()

def is_subpath(str_child, str_parent):
  try:
    path_child = Path(str_child).resolve()
    path_parent = Path(str_parent).resolve()
    path_child.relative_to(path_parent)
    return True
  except ValueError:
    return False

def is_system_macro(cursor):
  if cursor.spelling in user_macros:
    return False

  loc = cursor.location
  if loc is None or loc.file is None:
    return True

  macro_path = Path(loc.file.name).resolve()
  if macro_path == target_header:
    return False

  macro_dir = macro_path.parent
  if any(is_subpath(macro_path, d) for d in include_dirs):
    return False

  return True

def get_relative_path_from_include_dirs(fp):
  _fp = str(Path(fp).resolve())
  for d in include_dirs:
    _d = str(Path(d).resolve())
    if _fp.startswith(_d):
      return _fp.removeprefix(_d)[1:]
  return fp

  if cursor.location and cursor.location.file:
    fp = '"' + get_relative_path_from_include_dirs(cursor.location.file.name) + '"'
    print(f"{indent}/* file:{fp} line:{cursor.location.line} kind:{str_kind} */")
  elif cursor.location:
    print(f"{indent}/* file:<None> line:{cursor.location.line} kind:{str_kind} */")

words_produced = dict()
words_consumed = dict()
words_referenced = dict()
def walk(cursor, indent):
  if not is_system_macro(cursor):
    if cursor.location:
      if cursor.location.file:
        loc_path = get_relative_path_from_include_dirs(cursor.location.file.name)
      else:
        loc_path = "<None>"
      str_loc = f"{loc_path}:{cursor.location.line}:{cursor.location.column}"
    else:
      str_loc = "<None>"
    str_kind = str(cursor.kind).split(".")[-1]

    # str_info = "\t".join([str_loc, cursor.get_usr(), str_kind, cursor.spelling])
    str_info = "\t".join([str_loc, str_kind, cursor.spelling])
    print(f"{indent}{str_info}")

    if cursor.kind in producer_kinds:
      words_produced[cursor.spelling] = str_loc
    elif cursor.kind in consumer_kinds:
      if cursor.spelling in words_consumed:
        words_consumed[cursor.spelling].add(str_loc)
      else:
        words_consumed[cursor.spelling] = set([str_loc])

      if cursor.referenced is None:
        pass
      elif cursor.referenced.spelling in words_referred:
        words_referenced[cursor.referenced.spelling].add(str_loc)
      else:
        words_referenced[cursor.referenced.spelling] = set([str_loc])

  for c in cursor.get_children():
    walk(c, indent + "  ")

index = Index.create()
header_ast = index.parse(args.extras[0], args = [
  ("-D" + macro) for macro in args.defines
] + [
  ("-I" + dir) for dir in args.include_dirs
], options = TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
walk(header_ast.cursor, "")

set_words_produced = set(words_produced.keys())
set_words_consumed = set(words_consumed.keys())
set_words_referenced = set(words_referenced.keys())

print(list(set_words_produced - set_words_consumed - set_words_referenced))
print(list(set_words_referenced - set_words_produced))
