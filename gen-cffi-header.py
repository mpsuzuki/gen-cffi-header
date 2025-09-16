#!/usr/bin/env python

import argparse
import sys
import re
import os
import glob

regex_numeric = re.compile(
  r"^(0[xX][0-9a-fA-F]+|0[0-7]+|[1-9][0-9]*|0)[uU]{0,2}[lL]{0,2}$",
  re.VERBOSE
)

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
parser.add_argument("--save-temps", action = "store_true",
                    help = "Keep temporary files (remove by default)")
parser.add_argument("extras", nargs = 1,
                    help = "Path to the header file")
args = parser.parse_args()

from clang.cindex import Index, CursorKind, TypeKind, TranslationUnit

kind_decl_map = {
  CursorKind.UNEXPOSED_DECL: "unexposed",
  CursorKind.STRUCT_DECL: "struct",
  CursorKind.UNION_DECL: "union",
  CursorKind.CLASS_DECL: "class",
  CursorKind.ENUM_DECL: "enum",
  CursorKind.ENUM_CONSTANT_DECL: "enum_const",
  CursorKind.FUNCTION_DECL: "function",
  CursorKind.VAR_DECL: "var",
  CursorKind.PARM_DECL: "parm",
  CursorKind.TYPE_ALIAS_DECL: "type_alias",
  CursorKind.TYPEDEF_DECL: "typedef",
  CursorKind.CONCEPT_DECL: "concept",
  # CursorKind.USING_DECL: "using",

  # CursorKind.OBJ_C_INTERFACE_DECL: "interface",
  # CursorKind.OBJ_C_CATEGORY_DECL: "category",
  # CursorKind.OBJ_C_PROTOCOL_DECL: "protocol",
  # CursorKind.OBJ_C_PROPERTY_DECL: "property",
  # CursorKind.OBJ_C_IVAR_DECL: "ivar",
  # CursorKind.OBJ_C_INSTANCE_METHOD_DECL: "instance_method",
  # CursorKind.OBJ_C_CLASS_METHOD_DECL: "class_method",
  # CursorKind.OBJ_C_IMPLEMENTATION_DECL: "implementation",
  # CursorKind.OBJ_C_CATEGORY_IMPL_DECL: "category_impl",
}

def normalize_spaces(s):
  return " ".join(s.split())

def resolve_elaborated_type(t):
  if t.kind == TypeKind.ELABORATED:
    return t.get_named_type()
  return t

def has_typedef_sibling(cursor):
  parent = cursor.semantic_parent
  for sibling in parent.get_children():
    if sibling.kind == CursorKind.TYPEDEF_DECL:
      t = sibling.underlying_typedef_type
      if t.kind == TypeKind.ELABORATED:
        t = t.get_named_type()
      if t.get_declaration() == cursor:
        return True
  return False

def has_valid_spelling(cursor):
  return (len(cursor.spelling.split()) == 1)

def get_fields_from_struct_or_union(decl, indent = "  ", anon_counter = [1]):
  fields = []
  for child in decl.get_children():
    loc = child.location
    if loc and loc.file:
      loc_info = f" // from {loc.file.name}:{loc.line}:{loc.column}"
    else:
      loc_info = ""

    if child.kind == CursorKind.FIELD_DECL:
      field_type = child.type
      field_name = child.spelling

      if field_type.kind == TypeKind.CONSTANTARRAY:
        elem_type  = field_type.element_type.spelling
        array_size = field_type.element_count
        fields.append(f"{indent}{elem_type} {field_name}[{array_size}];")
      else:
        fields.append(f"{indent}{field_type.spelling} {field_name};")
    elif child.kind in {CursorKind.STRUCT_DECL, CursorKind.UNION_DECL}:
      if has_valid_spelling(child.type) and has_valid_spelling(child):
        fields.append(f"{indent}{child.type.spelling} {child.spelling};")
      else:
        kind_str   = kind_decl_map.get(child.kind, "unknown")
        type_name  = f"__anon_{kind_str}_{anon_counter[0]}"
        field_name = f"__anon_{kind_str}_{anon_counter[0]}_value"
        anon_counter[0] += 1

        subfields = get_fields_from_struct_or_union(child, indent + indent, anon_counter)
        body = "\n".join(subfields)
        fields.append(f"{indent}{kind_str} {type_name} {{{loc_info}\n{body}\n{indent}}} {field_name};")
  return fields

def get_constants_from_enum(decl):
  constants = []
  for child in decl.get_children():
    if child.kind == CursorKind.ENUM_CONSTANT_DECL:
      name = child.spelling
      val  = child.enum_value
      if val < 0x10:
        constants.append(f"  {name} = {val},")
      elif val < 0x100:
        constants.append(f"  {name} = {val},")
      elif val < 0x10000:
        constants.append(f"  {name} = 0x{val:04X},")
      elif val < 0x100000000:
        constants.append(f"  {name} = 0x{val:08X},")
      else:
        constants.append(f"  {name} = {val},")
  return constants


def emit_inline_typedef_with_body(cursor, args):
  if cursor.kind != CursorKind.TYPEDEF_DECL:
    return None

  typedef_name = cursor.spelling
  t = cursor.underlying_typedef_type

  if t.kind == TypeKind.ELABORATED:
    t = t.get_named_type()

  decl = t.get_declaration()
  tag_name = decl.spelling

  #if t.kind not in {TypeKind.UNION, TypeKind.RECORD}:
  #  return None

  if not decl.is_definition():
    return None
  kind_str = kind_decl_map.get(decl.kind, "unknown")

  if kind_str in {"struct", "union"}:
    fields = get_fields_from_struct_or_union(decl)
    body = "\n".join(fields)
  elif kind_str == "enum":
    constants = get_constants_from_enum(decl)
    body = "\n".join(constants)
  else:
    return None
#  return f"typedef {kind_str} {{\n{body}\n}} {typedef_name};"
  if tag_name:
    return (
      f"{kind_str} {tag_name} {{\n{body}\n}};\n"
      f"typedef {kind_str} {tag_name} {typedef_name};"
    )
  else:
    return f"typedef {kind_str} {{\n{body}\n}} {typedef_name};"

def emit_typedef(cursor, args):
  if cursor.kind != CursorKind.TYPEDEF_DECL:
    return None

  typedef_name = cursor.spelling
  t = cursor.underlying_typedef_type

  # Primitive types
  if normalize_spaces(t.spelling) in {
    "unsigned char", "unsigned short", "unsigned int", "unsigned long",
    "char", "short", "int", "long",
    "float", "double", "void", "void *",
  }:
    return f"typedef {t.spelling} {typedef_name};"

  append_output("/* " + str(t.kind) + " " + str(t.get_pointee().kind) + " */", "verbose")

  # Pointer to struct
  if t.kind == TypeKind.POINTER:
    pointee = resolve_elaborated_type(t.get_pointee())
    if pointee.kind == TypeKind.RECORD:
      struct_name = pointee.get_declaration().spelling
      return f"typedef struct {struct_name} *{typedef_name};"
    elif pointee.kind == TypeKind.FUNCTIONPROTO:
      fp = t.get_pointee()
      return_type = fp.get_result().spelling
      arg_types = [arg.spelling for arg in fp.argument_types()]
      args = ", ".join(arg_types)
      return f"typedef {return_type} (*{typedef_name})({args});"

  # Direct struct typedef
  if t.kind == TypeKind.RECORD:
    struct_name = t.get_declaration().spelling
    return f"typedef struct {struct_name} {typedef_name};"

  # Enum typedef
  if t.kind == TypeKind.ENUM:
    enum_name = t.get_declaration().spelling
    return f"typedef enum {enum_name} {typedef_name};"

  # Function pointer typedef
  if t.kind == TypeKind.FUNCTIONPROTO:
    return f"typedef {t.spelling} {typedef_name};"

  # Typedef of another typedef
  if t.kind == TypeKind.TYPEDEF:
    return f"typedef {t.spelling} {typedef_name};"

  # Fixed-size array typedef
  if t.kind == TypeKind.CONSTANTARRAY:
    element_type = t.element_type.spelling
    size = t.element_count
    return f"typedef {element_type} {typedef_name}[{size}];"

  str_typedef_with_body = emit_inline_typedef_with_body(cursor, args)
  if str_typedef_with_body:
    return "\n" + str_typedef_with_body + "\n"

  return None

def emit_struct_union_enum_decl(cursor, args, anon_union_counter = 0):
  if cursor.kind not in { CursorKind.STRUCT_DECL, CursorKind.UNION_DECL, CursorKind.ENUM_DECL }:
    return None

  if has_typedef_sibling(cursor):
    append_output(f"/* has sibling, do not emit now */", "verbose")
  elif cursor.kind == CursorKind.STRUCT_DECL:
    fields = get_fields_from_struct_or_union(cursor, indent = "  ")
    body = "\n".join(fields)
    if has_valid_spelling(cursor):
      return f"struct {cursor.spelling} {{\n{body}\n}};"
    else:
      return None
  elif cursor.kind == CursorKind.UNION_DECL:
    fields = get_fields_from_struct_or_union(cursor, indent = "  ")
    body = "\n".join(fields)
    if has_valid_spelling(cursor):
      return f"union {cursor.spelling} {{\n{body}\n}};"
    else:
      return None
  elif cursor.kind == CursorKind.ENUM_DECL:
    constants = get_constants_from_enum(cursor)
    body = "\n".join(constants)
    if has_valid_spelling(cursor):
      return f"enum {cursor.spelling} {{\n{body}\n}};"
    else:
      return f"enum {{\n{body}\n}};"
  else:
    return None

def emit_function_decl(cursor, args):
  if cursor.kind != CursorKind.FUNCTION_DECL:
    return None

  func_name = cursor.spelling
  return_type = cursor.result_type.spelling

  params = []
  for arg in cursor.get_arguments():
    arg_type = arg.type.spelling
    arg_name = arg.spelling or "arg"
    params.append(f"{arg_type} {arg_name}")

  param_str = ", ".join(params)
  return f"{return_type} {func_name}({param_str});"

from pathlib import Path
target_header = Path(args.extras[0]).resolve()
include_dirs = [Path(d).resolve() for d in args.include_dirs]
user_macros = [d.split("=", 1)[0].strip() for d in args.defines]
dict_c_identifier = {}
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

def path_to_c_identifier(path, count = 2):
  path = re.sub(r"^[\\/]+", "", path)
  path = "_".join(Path(path).parts[(0 - count):])
  return re.sub(r"[^a-zA-Z0-9_]", "_", path)

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

output_items = []
def append_output(s, k):
  itm = AttrDict({})
  itm.body = s
  itm.kind = k
  output_items.append(itm)

def process_macro_definition(cursor):
  macro = AttrDict()
  macro.is_primitive = False

  loc = cursor.location
  if loc.file:
    c_path = path_to_c_identifier(loc.file.name)
    macro.location = AttrDict({
      "path": loc.file.name,
      "line": loc.line,
      "column": loc.column
    })
    macro.location_cstr = f"{c_path}_L{loc.line}_C{loc.column}"
    dict_c_identifier[loc.file.name] = c_path
    dict_c_identifier[c_path] = loc.file.name

  macro.name = cursor.spelling
  tokens = list(cursor.get_tokens())

  if len(tokens) == 1:
    return macro

  if len(tokens) == 2 and tokens[0].spelling == macro.name and is_oct_dec_hex(tokens[1].spelling):
    macro.value = tokens[1].spelling
    macro.is_primitive = True
    return macro

  value_tokens = tokens[1:]
  if value_tokens[0].spelling == "<": # FreeType defines pathname for header location by <...>
    macro.value = "".join(t.spelling for t in value_tokens)
  else:
    macro.value = " ".join(t.spelling for t in value_tokens)

  return macro

todo_macros = dict({})

index = Index.create()
header_ast = index.parse(args.extras[0], args = [
  ("-D" + macro) for macro in args.defines
] + [
  ("-I" + dir) for dir in args.include_dirs
], options = TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)


for cursor in header_ast.cursor.get_children():
  append_output("\n/* " + str(cursor.spelling) + " " + str(cursor.kind) + " */", "verbose")

  if cursor.kind == CursorKind.MACRO_DEFINITION:
    if is_system_macro(cursor):
      continue

    m = process_macro_definition(cursor)
    if m.is_primitive and m.value:
      append_output(f"#define {m.name} {m.value}", "macro_defined")
    else:
      if m.value:
        append_output(f"/* {m.name} is not primitive */", "macro_non_primitive")
        todo_macros[m.name] = output_items[-1]
        todo_macros[m.name].macro = m
      else:
        append_output(f"/* {m.name} is empty */", "macro_empty")

  # elif cursor.kind == CursorKind.VAR_DECL:
  #   TODO

  elif cursor.kind == CursorKind.TYPEDEF_DECL:
    typedef = emit_typedef(cursor, args)
    if typedef:
      append_output(typedef, "typedef")
  elif cursor.kind in { CursorKind.STRUCT_DECL, CursorKind.UNION_DECL, CursorKind.ENUM_DECL }:
    if not cursor.is_definition():
      append_output(f"/* {cursor.spelling} is not a definition */", "verbose")
      continue

    str_decl = emit_struct_union_enum_decl(cursor, args)
    if str_decl:
      append_output("\n" + str_decl + "\n", "struct_union_enum")
  elif cursor.kind == CursorKind.FUNCTION_DECL:
    str_decl = emit_function_decl(cursor, args)
    if str_decl:
      append_output(str_decl, "function")

pat_tmpfiles = os.path.join(os.getcwd(), "macro_eval_*")
for fp_tmp in glob.glob(pat_tmpfiles):
  try:
    os.remove(fp_tmp)
    print(f"Deleted {fp_tmp}", file = sys.stderr)
  except Exception as e:
    print(f"Failed to delete {fp_tmp}: {e}", file = sys.stderr)

def walk(cursor, indent):
  for c in cursor.get_children():
    if c.kind == CursorKind.ENUM_CONSTANT_DECL and c.enum_value:
      macro_name = re.sub(r"^__", "", c.spelling)
      if c.enum_value < 0x10:
        macro_define = f"{indent}#define {macro_name}\t{c.enum_value}"
      elif c.enum_value < 0x100:
        macro_define = f"{indent}#define {macro_name}\t0x{c.enum_value:02X}"
      elif c.enum_value < 0x10000:
        macro_define = f"{indent}#define {macro_name}\t0x{c.enum_value:04X}"
      elif c.enum_value <= 0xFFFFFFFF:
        macro_define = f"{indent}#define {macro_name}\t0x{c.enum_value:08X}"
      else:
        macro_define = f"{indent}#define {macro_name}\t0x{c.enum_value:X}"

#      if macro_name in todo_macros:
#        todo_macros[macro_name].body = macro_define
#        todo_macros[macro_name].kind = "macro_defined"

    walk(c, indent + "  ")

if len(todo_macros) > 0:
  #for macro_name, itm in todo_macros.items():
  #  print(f"/* {macro_name}, {itm.body}, {itm.kind} */")
  import tempfile
  with tempfile.NamedTemporaryFile( mode = "w+",
                                    suffix = ".h",
                                    dir = os.getcwd(),
                                    prefix = "macro_eval_",
                                    delete = False # not(args.save_temps)
                                  ) as fh_tmp:
    print(fh_tmp.name)
    print(f"#include \"{target_header}\"", file = fh_tmp)
    for macro_name, itm in todo_macros.items():
      m = itm.macro
      print(f"enum __anon_{m.name}_{m.location_cstr} {{__{m.name} = {m.value}}};",
            file = fh_tmp)

    macros_ast = index.parse(fh_tmp.name, args = [
      ("-D" + macro) for macro in args.defines
    ] + ["-I ."] + [
      ("-I" + dir) for dir in args.include_dirs
    ], options = TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)

    walk(macros_ast.cursor, "")

for itm in output_items:
  if itm.kind == "verbose":
    if args.verbose:
      print(itm.body)
  else:
    print(itm.body)
