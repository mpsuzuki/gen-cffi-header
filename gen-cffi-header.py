#!/usr/bin/env python

from clang.cindex import Index, CursorKind, TypeKind

def resolve_elaborated_type(t):
  if t.kind == TypeKind.ELABORATED:
    return t.get_named_type()
  return t

def emit_inline_typedef_with_body(cursor):
  if cursor.kind != CursorKind.TYPEDEF_DECL:
    return None

  typedef_name = cursor.spelling
  t = cursor.underlying_typedef_type

  if t.kind == TypeKind.ELABORATED:
    t = t.get_named_type()

  decl = t.get_declaration()

  #if t.kind not in {TypeKind.UNION, TypeKind.RECORD}:
  #  return None

  if decl.kind == CursorKind.UNION_DECL:
    kind_str = "union"
  elif decl.kind == CursorKind.STRUCT_DECL:
    kind_str = "struct"
  else:
    kind_str = "record"

  if not decl.is_definition():
    return None

  fields = []
  for field in decl.get_children():
    if field.kind == CursorKind.FIELD_DECL:
      field_type = field.type.spelling
      field_name = field.spelling
      fields.append(f"    {field_type} {field_name};")
  body = "\n".join(fields)
  return f"typedef {kind_str} {{\n{body}\n}} {typedef_name};"

def emit_typedef(cursor):
  if cursor.kind != CursorKind.TYPEDEF_DECL:
    return None

  typedef_name = cursor.spelling
  t = cursor.underlying_typedef_type

  # Primitive types
  if t.kind in {
    TypeKind.INT, TypeKind.UINT, TypeKind.SHORT, TypeKind.USHORT,
    TypeKind.LONG, TypeKind.ULONG, TypeKind.CHAR_S, TypeKind.CHAR_U,
    TypeKind.FLOAT, TypeKind.DOUBLE, TypeKind.VOID
  }:
    return f"typedef {t.spelling} {typedef_name};"

  print(t.kind)
  print(t.get_pointee().kind)

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

index = Index.create()
tu = index.parse("test-variable.h", args = [
  "-I/opt/homebrew/opt/freetype/include/freetype2",
  "-I/opt/homebrew/opt/libpng/include/libpng16"
])

for cursor in tu.cursor.get_children():
  print("")
  if cursor.kind.is_declaration():
    print(cursor.spelling, cursor.kind)

  typedef = emit_typedef(cursor)
  if typedef:
    print(typedef)
