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
parser.add_argument("--word-modification", type = str, default = "NONE",
                    help = "Mode of field/type modification: {ALWAYS|MINIMUM|LIST|HYBRID}")
parser.add_argument("--modify-words-in", type = str, default = None,
                    help = "Pathname of the list of the words to be modified")
parser.add_argument("--modifier-prefix", type = str, default = "",
                    help = "String to insert before the words to be modified")
parser.add_argument("--modifier-suffix", type = str, default = "_",
                    help = "String to append after the words to be modified")
parser.add_argument("extras", nargs = 1,
                    help = "Path to the header file")
args = parser.parse_args()

target_header = Path(args.extras[0]).resolve()
include_dirs = [Path(d).resolve() for d in args.include_dirs]

args.word_modification = args.word_modification.upper()
if args.modify_words_in is not None and args.word_modification == "LIST":
  with open(args.modify_words_in, "r") as fh:
    args.modify_words_in = set([])
    for _line in fh.read().split("\n"):
      _toks = re.split(r"[^0-9A-Za-z_]", _line)
      if len(_toks) > 0:
        args.modify_words_in.add(_toks[0])

if args.word_modification in {"MINIMUM", "HYBRID"}:
  import keyword
  if args.modify_words_in is None:
    args.modify_words_in = set([])
  args.modify_words_in.update(keyword.kwlist)

def modify_word(word_original):
  if args.word_modification == "NONE":
    return word_original
  elif args.word_modification == "ALWAYS" or word_original in args.modify_words_in:
    return args.modifier_prefix + word_original + args.modifier_suffix
  else:
    return word_original

def get_modified_spelling_at_cursor(cursor, word_to_modify):
  # print(f"\tget_modified_spelling_at_cursor({cursor.spelling}, {word_to_modify})")
  outs = []
  for token in cursor.translation_unit.get_tokens(extent = cursor.extent):
    if token.spelling == word_to_modify:
      outs.append(modify_word(token.spelling))
      # print(f"\t\t\t{token.spelling} -> {outs[-1]}")
    else:
      outs.append(token.spelling)
  return " ".join(outs)

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
    if args.debug:
      print(f"{indent}/* file:{fp} line:{cursor.location.line} kind:{str_kind} */")
  elif cursor.location:
    if args.debug:
      print(f"{indent}/* file:<None> line:{cursor.location.line} kind:{str_kind} */")

def has_single_token_spelling(cursor):
  return (len(cursor.spelling.split()) == 1)

def get_cursor_modifier(header_ast):
  words_produced = dict()
  words_consumed = dict()

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
      if args.debug:
        print(f"{indent}{str_info}")

      itm = AttrDict()
      itm.location_str = str_loc
      itm.cursor = cursor

      if cursor.kind in producer_kinds:
        if has_single_token_spelling(cursor):
          itm.users = set({})
          words_produced[cursor.spelling] = itm
        else:
          if args.debug:
            print(f"{indent}# this declaration has no name, do not collect")
      elif cursor.kind in consumer_kinds and cursor.referenced:
        ref_spell = cursor.referenced.spelling
        if ref_spell in words_consumed:
          words_consumed[ref_spell].add(itm)
        else:
          words_consumed[ref_spell] = set([itm])
        if ref_spell in words_produced:
          words_produced[ref_spell].users.add(itm)

    for c in cursor.get_children():
      walk(c, indent + "  ")

  walk(header_ast.cursor, "")

  if args.debug:
    set_words_produced = set(words_produced.keys())
    set_words_consumed = set(words_consumed.keys())
    print(set_words_consumed - set_words_produced)

  cursor_modifier = dict({})
  for spelling, itm in words_produced.items():
    if args.debug:
      print(f"spelling={spelling}, {len(itm.users)} users")
    # if spelling not in words_consumed:
    #   continue

    spelling_modified = modify_word(spelling)
    if spelling_modified != spelling:
      if args.debug:
        print(f"At {itm.location_str}: {spelling} -> {spelling_modified}")
      cursor_modifier[itm.cursor] = AttrDict({
        "location_str": itm.location_str,
        "spelling_old": spelling,
        "spelling": spelling_modified
      })

      for itm_user in itm.users:
        spelling_user_modified = get_modified_spelling_at_cursor(itm_user.cursor, spelling)
        if args.debug:
          print(f"At {itm_user.location_str}: "
                f"{itm_user.cursor.spelling} -> "
                f"{spelling_user_modified}"
          )
        cursor_modifier[itm_user.cursor] = AttrDict({
          "location_str": itm_user.location_str,
          "spelling_old": itm_user.cursor.spelling,
          "spelling": spelling_user_modified
        })

      if args.debug:
        print("")

  return cursor_modifier

index = Index.create()
header_ast = index.parse(args.extras[0], args = [
  ("-D" + macro) for macro in args.defines
] + [
  ("-I" + dir) for dir in args.include_dirs
], options = TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)

cursor_modifier = get_cursor_modifier(header_ast)

for cursor, itm in cursor_modifier.items():
  print(f"{itm.location_str} {itm.spelling_old} -> {itm.spelling}")
