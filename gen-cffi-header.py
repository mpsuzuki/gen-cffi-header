#!/usr/bin/env python

import argparse
import sys
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

from clang.cindex import Index, CursorKind, TypeKind

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
  return f"typedef {kind_str} {{\n{body}\n}} {typedef_name};"
#  if tag_name:
#    return (
#      f"{kind_str} {tag_name} {{\n{body}\n}};\n"
#      f"typedef {kind_str} {tag_name} {typedef_name};"
#    )
#  else:
#    return f"typedef {kind_str} {{\n{body}\n}} {typedef_name};"

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

  if args.verbose:
    print("/* " + str(t.kind) + " " + str(t.get_pointee().kind) + " */")

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
    if args.verbose:
      print(f"/* has sibling, do not emit now */")
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

index = Index.create()
tu = index.parse(args.extras[0], args = [
  ("-I" + dir) for dir in args.include_dirs
] + [
  ("-D" + macro) for macro in args.defines
])

for cursor in tu.cursor.get_children():
  if cursor.kind.is_declaration():
    if args.verbose:
      print("/* " + str(cursor.spelling) + " " + str(cursor.kind) + " */")

  if cursor.kind == CursorKind.TYPEDEF_DECL:
    typedef = emit_typedef(cursor, args)
    if typedef:
      print(typedef)
  elif cursor.kind in { CursorKind.STRUCT_DECL, CursorKind.UNION_DECL, CursorKind.ENUM_DECL }:
    if not cursor.is_definition():
      if args.verbose:
        print(f"/* {cursor.spelling} is not a definition */")
      continue

    str_decl = emit_struct_union_enum_decl(cursor, args)
    if str_decl:
      print("\n" + str_decl + "\n")
  elif cursor.kind == CursorKind.FUNCTION_DECL:
    str_decl = emit_function_decl(cursor, args)
    if str_decl:
      print(str_decl)
