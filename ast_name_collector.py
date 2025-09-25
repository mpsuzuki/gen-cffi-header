import re
import keyword
from enum import Enum
from pathlib import Path
from clang.cindex import Index, CursorKind, TokenKind, TypeKind, TranslationUnit

from attrdict import AttrDict

class ASTNameCollector:
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
      self.debug = False
      self.selection = type(self).Selection.NONE
      self.name_coverage = set({})
      self.prefix = ""
      self.suffix = "_"
      self.get_relative_path = None

    def dump_extent(self, obj, prefix = "", indent = ""):
      path_file = obj.extent.start.file.name
      if self.get_relative_path:
        path_file = self.get_relative_path(path_file)
      print(f"{indent}{prefix}: {str(obj.kind)} "
            f"\'{str(obj.spelling)}\'"
            f" @{path_file}:"
            f"{obj.extent.start.line}:"
            f"{obj.extent.start.column}.."
            f"{obj.extent.end.column}"
      )

    def dump_tokens_at_cursor(self, cursor, indent = ""):
      for token in cursor.translation_unit.get_tokens(extent = cursor.extent):
        self.dump_extent(token, prefix = "token", indent = indent)

    @staticmethod
    def cat_tokens(cursor):
      return " ".join([t.spelling
                       for t in cursor.translation_unit.get_tokens(extent = cursor.extent)
                      ])

    @staticmethod
    def load_name_set_from_file(path_list):
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
        self.name_coverage |= type(self).load_name_set_from_file(path_list)

    def modify_name(self, n, kind = None):
      if self.selection.is_none():
        return n
      if kind is not None and kind not in self.emitter_kinds:
        return n
      if (self.selection.is_always() or n in self.name_coverage):
        return self.prefix + n + self.suffix
      return n

    def get_modified_spelling_at_cursor(self, cursor, name_to_modify, check_kind = False):
      if self.debug:
        self.dump_extent(cursor, "cursor", self.indent * 2)
        self.dump_tokens_at_cursor(cursor, self.indent * 3)
      modified = []
      for token in cursor.translation_unit.get_tokens(extent = cursor.extent):
        if token.spelling != name_to_modify or token.location != cursor.location:
          modified.append(token.spelling)
        elif check_kind:
          modified.append(self.modify_name(token.spelling, cursor.kind))
        else:
          modified.append(self.modify_name(token.spelling))
      if self.debug:
        spelling_modified = " ".join(modified)
        print(f"{self.indent * 2}get_modified_spelling_at_cursor(): "
              f"{cursor.spelling} -> {spelling_modified}")
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
      self.target_source = None
      if defines:
        self.defines = defines
      else:
        self.defines = []

      if include_dirs:
        self.include_dirs = include_dirs
      else:
        self.include_dirs = []

      self.user_macros = [d.split("=", 1)[0].strip() for d in self.defines]

    def is_system_macro(self, cursor):
      if cursor.spelling in self.user_macros:
        return False

      loc = cursor.location
      if loc is None or loc.file is None:
        return True

      macro_path = Path(loc.file.name).resolve()
      if macro_path == self.target_source:
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

  def __init__(self, indent = "  "):
    self.debug = None
    self.source = AttrDict()
    self.parsed_ast = None
    self.modifier = type(self).Modifier()
    self.cpp = type(self).Cpp()

    self.indent = indent
    self.modifier.indent = self.indent
    self.cpp.indent = self.indent
    self.modifier.get_relative_path = self.cpp.get_relative_path

  def set_indent(indent):
    self.indent = indent
    self.modifier.indent = indent
    self.cpp.indent = indent
    return self

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

  def get_location_str_from_object(self, object):
    if object.location:
      if object.location.file:
        loc_path = self.cpp.get_relative_path(object.location.file.name)
      else:
        loc_path = "<None>"
      str_loc = f"{loc_path}:{object.location.line}:{object.location.column}"
    elif object.extent:
      if object.extent.file:
        loc_path = self.cpp.get_relative_path(object.extent.start.file.name)
      else:
        loc_path = "<None>"
      str_loc = f"{loc_path}:{object.extent.start.line}:{object.extent.start.column}"
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
        adic.location_str = self.get_location_str_from_object(cursor)
      return adic

    def create_attrdict_on_token(token, location_str = None):
      adic = AttrDict()
      adic.token = token
      if location_str:
        adic.location_str = location_str
      else:
        adic.location_str = self.get_location_str_from_object(token)
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
    # names to be modified or preserved is delayed to the generation
    # of substitution_graph.
    def walk(cursor, indent):
      if not self.cpp.is_system_macro(cursor):
        str_loc = self.get_location_str_from_object(cursor)
        str_kind = str(cursor.kind).split(".")[-1]
        str_info = "\t".join([str_loc, str_kind, cursor.spelling])

        if cursor.kind in type(self).PRODUCER_KINDS:
          update_dic_emitters(cursor, location_str = str_loc, indent = indent)
        elif cursor.kind in type(self).CONSUMER_KINDS and cursor.referenced:
          update_dic_receivers(cursor, location_str = str_loc, indent = indent)

      for c in cursor.get_children():
        walk(c, indent + "  ")

    walk(header_ast.cursor, "")

    if self.debug:
      set_name_emitters  = set(dic_emitters.keys())
      set_name_receivers = set(dic_receivers.keys())
      # print(set_name_receivers - set_name_emitters)

    substitution_graph = dict({})
    for e_spell, e_adic in dic_emitters.items():
      e_spell_modified = self.modifier.modify_name(e_spell, e_adic.cursor.kind)
      if e_spell_modified != e_spell:
        substitution_graph[e_adic.cursor] = AttrDict({
          "location_str": e_adic.location_str,
          "spelling_old": e_spell,
          "spelling": e_spell_modified
        })
        if self.debug:
          print(f"At {e_adic.location_str}: {e_spell} -> {e_spell_modified}")
          self.modifier.dump_extent(e_adic.cursor, "cursor", self.indent)
          self.modifier.dump_tokens_at_cursor(e_adic.cursor, self.indent * 2)
        for r_adic in e_adic.receivers:
          r_spell_modified = self.modifier.get_modified_spelling_at_cursor(r_adic.cursor, e_spell, check_kind = False)
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

        if self.debug:
          print("")

    return substitution_graph
