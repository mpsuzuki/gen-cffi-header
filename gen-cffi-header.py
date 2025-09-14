#!/usr/bin/env python

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

def get_fields_from_struct_or_union(decl):
  fields = []
  for field in decl.get_children():
    if field.kind == CursorKind.FIELD_DECL:
      field_type = field.type.spelling
      field_name = field.spelling
      fields.append(f"    {field_type} {field_name};")
  return fields

def get_constants_from_enum(decl):
  constants = []
  for child in decl.get_children():
    if child.kind == CursorKind.ENUM_CONSTANT_DECL:
      name = child.spelling
      val  = child.enum_value
      if val < 0x10:
        constants.append(f"    {name} = {val},")
      elif val < 0x100:
        constants.append(f"    {name} = {val},")
      elif val < 0x10000:
        constants.append(f"    {name} = 0x{val:04X},")
      elif val < 0x100000000:
        constants.append(f"    {name} = 0x{val:08X},")
      else:
        constants.append(f"    {name} = {val},")
  return constants


def emit_inline_typedef_with_body(cursor):
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

def emit_typedef(cursor):
  if cursor.kind != CursorKind.TYPEDEF_DECL:
    return None

  typedef_name = cursor.spelling
  t = cursor.underlying_typedef_type

  # Primitive types
  if normalize_spaces(t.spelling) in {
    "unsigned char", "unsigned short", "unsigned int", "unsigned long",
    "char", "short", "int", "long",
    "float", "double", "void"
  }:
    return f"typedef {t.spelling} {typedef_name};"

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

  str_typedef_with_body = emit_inline_typedef_with_body(cursor)
  if str_typedef_with_body:
    return str_typedef_with_body

  return None

def emit_struct_union_enum_decl(cursor):
  if cursor.kind not in { CursorKind.STRUCT_DECL, CursorKind.UNION_DECL, CursorKind.ENUM_DECL }:
    return None

  if not cursor.spelling:
    print(f"/* anonymous structure, do not emit now */")
    pass
  elif has_typedef_sibling(cursor):
    print(f"/* has sibling, do not emit now */")
    pass
  elif cursor.kind == CursorKind.STRUCT_DECL:
    print(f"/* cursor.kind = {str(cursor.kind)} */")
    fields = get_fields_from_struct_or_union(cursor)
    body = "\n".join(fields)
    return f"struct {cursor.spelling} {{\n{body}\n}};"
  elif cursor.kind == CursorKind.UNION_DECL:
    print(f"/* cursor.kind = {str(cursor.kind)} */")
    fields = get_fields_from_struct_or_union(cursor)
    body = "\n".join(fields)
    return f"union {cursor.spelling} {{\n{body}\n}};"
  elif cursor.kind == CursorKind.ENUM_DECL:
    print(f"/* cursor.kind = {str(cursor.kind)} */")
    constants = get_constants_from_enum(cursor)
    body = "\n".join(constants)
    return f"enum {cursor.spelling} {{\n{body}\n}};"
  else:
    print(f"/* cursor.kind = {str(cursor.kind)} */")
    return None

index = Index.create()
tu = index.parse("test-variable.h", args = [
  "-I/opt/homebrew/opt/freetype/include/freetype2",
  "-I/opt/homebrew/opt/libpng/include/libpng16"
])

for cursor in tu.cursor.get_children():
  if cursor.kind.is_declaration():
    print("/* " + str(cursor.spelling) + " " + str(cursor.kind) + " */")

  if cursor.kind == CursorKind.TYPEDEF_DECL:
    typedef = emit_typedef(cursor)
    if typedef:
      print(typedef)
  elif cursor.kind in { CursorKind.STRUCT_DECL, CursorKind.UNION_DECL, CursorKind.ENUM_DECL }:
    if not cursor.is_definition():
      print(f"/* {cursor.spelling} is not a definition */")
      continue

    str_decl = emit_struct_union_enum_decl(cursor)
    if str_decl:
      print(str_decl)

  print("")
