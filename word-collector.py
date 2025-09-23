#!/usr/bin/env python

import argparse
import sys
import re
import os
import glob
from pathlib import Path
from clang.cindex import Index, CursorKind, TypeKind, TranslationUnit

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

import keyword
from attrdict import AttrDict
from enum import Enum

class HeaderProcessor:
  PRODUCER_KINDS = {
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

  CONSUMER_KINDS = {
    CursorKind.TYPE_REF,
    CursorKind.DECL_REF_EXPR,
    CursorKind.MEMBER_REF_EXPR,
    CursorKind.CALL_EXPR,
    CursorKind.UNEXPOSED_EXPR,

    CursorKind.MACRO_INSTANTIATION,
  }

  @staticmethod
  def kind2str(k):
    s = str(k).split(".")[-1].lower()
    s = re.sub(r"_decl$", "", s)
    s = re.sub(r"_expr$", "", s)
    return s

  @classmethod
  def str2kind(cls, str):
    for k in (cls.PRODUCER_KINDS | cls.CONSUMER_KINDS):
      s = cls.kind2str(k)
      if str == s:
        return k
    return None

  class Modifier:
    class Selection(Enum):
      NONE = 0
      ALWAYS = 1
      ALL = 1 # alias
      MINIMUM = 2
      LIST = 3
      HYBRID = 4

      @classmethod
      def from_string(cls, s):
        try:
          return cls[s.upper()]
        except:
          return cls.NONE

      def is_none(self):
        return (self == type(self).NONE)

      def is_always(self):
        return (self == type(self).ALWAYS)

      def is_all(self):
        return self.is_always()

      def needs_kwlist(self):
        return (self in {type(self).MINIMUM, type(self).HYBRID})

      def needs_list(self):
        return (self in {type(self).LIST, type(self).HYBRID})

    def __init__(self):
      self.emitter_kinds = {
        # safe even in C++
        CursorKind.ENUM_CONSTANT_DECL,
        CursorKind.FIELD_DECL,
        CursorKind.MACRO_INSTANTIATION,

        # safe in C, but unsafe in C++
        ## CursorKind.STRUCT_DECL,
        ## CursorKind.UNION_DECL,
        ## CursorKind.ENUM_DECL,
        ## CursorKind.TYPEDEF_DECL,
      }
      self.selection = type(self).Selection.NONE
      self.name_coverage = set({})
      self.prefix = ""
      self.suffix = "_"

    @staticmethod
    def get_name_set_from_file(path_list):
      name_set = None
      with open(path_list, "r") as fh:
        name_set = set({})
        for line in fh.read().split("\n"):
          tokens = re.split(r"[^0-9A-Za-z_]", line)
          if len(tokens) > 0:
            name_set.add(tokens[0])
      return name_set

    def set_selection_by_str(self, str_sel, path_list = None):
      self.selection = type(self).Selection.from_string(str_sel)
      if self.selection.needs_kwlist():
        self.name_coverage |= set(keyword.kwlist)

      if self.selection.needs_list():
        self.name_coverage |= type(self).get_name_set_from_file(path_list)

    def modify_name(self, n):
      if self.selection.is_none():
        return n
      if (self.selection.is_always() or n in self.name_coverage):
        return self.prefix + n + self.suffix
      return n

    def get_modified_spelling_at_cursor(self, cursor, name_to_modify):
      modified = []
      for token in cursor.translation_unit.get_tokens(extent = cursor.extent):
        if token.spelling == name_to_modify:
          modified.append(self.modify_name(token.spelling))
        else:
          modified.append(token.spelling)
      return " ".join(modified)

  class Cpp:
    @classmethod
    def is_subpath(cls, str_child, str_parent):
      try:
        path_child = Path(str_child).resolve()
        path_parent = Path(str_parent).resolve()
        path_child.relative_to(path_parent)
        return True
      except ValueError:
        return False

    def __init__(self, defines = None, include_dirs = None):
      if defines:
        self.defines = defines
      else:
        self.defines = []

      if include_dirs:
        self.include_dirs = include_dirs
      else:
        self.include_dirs = []

      self.user_macros = [d.split("=", 1)[0].strip() for d in args.defines]

    def is_system_macro(self, cursor):
      if cursor.spelling in self.user_macros:
        return False

      loc = cursor.location
      if loc is None or loc.file is None:
        return True

      macro_path = Path(loc.file.name).resolve()
      if macro_path == target_header:
        return False

      macro_dir = macro_path.parent
      if any(type(self).is_subpath(macro_path, d) for d in self.include_dirs):
        return False

      return True

    def get_relative_path(self, fp):
      _fp = str(Path(fp).resolve())
      for d in self.include_dirs:
        _d = str(Path(d).resolve())
        if _fp.startswith(_d):
          return _fp.removeprefix(_d)[1:]
      return fp

  def __init__(self):
    self.debug = None
    self.indent = "  "
    self.source = AttrDict()
    self.parsed_ast = None
    self.modifier = type(self).Modifier()
    self.cpp = type(self).Cpp()

  def set_debug(self, d):
    self.debug = d
    self.modifier.debug = d
    self.cpp.debug = d
    return self

  def set_emitter_kinds_by_csv(self, csv):
    ek = set({})
    for s in csv.split(","):
      k = type(self).str2kind(s.lower())
      if k:
        ek.add(k)
    self.modifier.emitter_kinds = ek
    return self

  @staticmethod
  def has_single_token_spelling(cursor):
    return (len(cursor.spelling.split()) == 1)

  def get_location_str_from_cursor(self, cursor):
    if cursor.location:
      if cursor.location.file:
        loc_path = self.cpp.get_relative_path(cursor.location.file.name)
      else:
        loc_path = "<None>"
      str_loc = f"{loc_path}:{cursor.location.line}:{cursor.location.column}"
    else:
      str_loc = "<None>"
    return str_loc

  def get_substitution_graph(self, header_ast):
    dic_emitters = dict()
    dic_receivers = dict()

    def create_attrdict_on_cursor(cursor, location_str = None):
      adic = AttrDict()
      adic.cursor = cursor
      if location_str:
        adic.location_str = location_str
      else:
        adic.location_str = self.get_location_str_from_cursor(cursor)
      return adic

    def update_dic_emitters(cursor, location_str = None, indent = ""):
      if not type(self).has_single_token_spelling(cursor):
        if self.debug:
          print(f"{indent}# \'{cursor.spelling}\' has no name, do not collect")
        return None

      adic = create_attrdict_on_cursor(cursor, location_str = location_str)
      adic.receivers = set({})
      dic_emitters[cursor.spelling] = adic
      return adic

    def update_dic_receivers(cursor, location_str = None, indent = ""):
      adic = create_attrdict_on_cursor(cursor, location_str)
      ref_spell = cursor.referenced.spelling
      if ref_spell in dic_receivers:
        dic_receivers[ref_spell].add(adic)
      else:
        dic_receivers[ref_spell] = set([adic])

      if ref_spell in dic_emitters:
        dic_emitters[ref_spell].receivers.add(adic)
      elif self.debug:
        print(f"{indent}# \'{ref_spell}\' is collected as emitters but never declared/defined")
      return adic

    # walk() collect all candidates of emitters and receivers,
    # walk() does not care the detailed kinds and names specified
    # by the options stored in self.modifier. Distinction of the
    # names to be modified or preserved is the role of Modifier,
    # not the role of the HeaderProcessor.
    def walk(cursor, indent):
      if not self.cpp.is_system_macro(cursor):
        str_loc = self.get_location_str_from_cursor(cursor)
        str_kind = str(cursor.kind).split(".")[-1]
        str_info = "\t".join([str_loc, str_kind, cursor.spelling])

        if cursor.kind in type(self).PRODUCER_KINDS:
          update_dic_emitters(cursor, location_str = str_loc, indent = indent)
        elif cursor.kind in type(self).CONSUMER_KINDS and cursor.referenced:
          update_dic_receivers(cursor, location_str = str_loc, indent = indent)

      for c in cursor.get_children():
        walk(c, indent + "  ")

    walk(header_ast.cursor, "")

    if args.debug:
      set_name_emitters  = set(dic_emitters.keys())
      set_name_receivers = set(dic_receivers.keys())
      # print(set_name_receivers - set_name_emitters)

    substitution_graph = dict({})
    for e_spell, e_adic in dic_emitters.items():
      e_spell_modified = self.modifier.modify_name(e_spell)
      if e_spell_modified != e_spell:
        if self.debug:
          print(f"At {e_adic.location_str}: {e_spell} -> {e_spell_modified}")
        substitution_graph[e_adic.cursor] = AttrDict({
          "location_str": e_adic.location_str,
          "spelling_old": e_spell,
          "spelling": e_spell_modified
        })

        for r_adic in e_adic.receivers:
          r_spell_modified = self.modifier.get_modified_spelling_at_cursor(r_adic.cursor, e_spell)
          if self.debug:
            print(f"{self.indent}At {r_adic.location_str}: "
                  f"{r_adic.cursor.spelling} -> "
                  f"{r_spell_modified}"
            )
          substitution_graph[r_adic.cursor] = AttrDict({
            "location_str": r_adic.location_str,
            "spelling_old": r_adic.cursor.spelling,
            "spelling": r_spell_modified
          })

        if args.debug:
          print("")

    return substitution_graph

header_processor = HeaderProcessor()
header_processor.set_debug(args.debug)
header_processor.set_emitter_kinds_by_csv(args.kinds_modify)
header_processor.modifier.prefix = args.modifier_prefix
header_processor.modifier.suffix = args.modifier_suffix
header_processor.modifier.set_selection_by_str(args.selection, args.modify_names_in)
header_processor.cpp.defines = args.defines
header_processor.cpp.include_dirs = args.include_dirs
index = Index.create()
header_ast = index.parse(args.extras[0], args = [
  ("-D" + macro) for macro in args.defines
] + [
  ("-I" + dir) for dir in args.include_dirs
], options = TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)

substitution_graph = header_processor.get_substitution_graph(header_ast)

for emitter_cursor, adic in substitution_graph.items():
  print(f"{adic.location_str} {adic.spelling_old} -> {adic.spelling}")
