#!/usr/bin/env python

from clang.cindex import Index, CursorKind, TypeKind

def is_struct_pointer_typedef(cursor):
  if cursor.kind != CursorKind.TYPEDEF_DECL:
    return False
  t = cursor.underlying_typedef_type
  return t.kind == TypeKind.POINTER and t.get_pointee().kind == TypeKind.RECORD

def get_struct_typedef(cursor):
  if cursor.kind != CursorKind.TYPEDEF_DECL:
    return None
  t = cursor.underlying_typedef_type
  if t.kind == TypeKind.POINTER and t.get_pointee().kind == TypeKind.RECORD:
    struct_cursor = t.get_pointee().get_declaration()
    struct_name = struct_cursor.spelling
    typedef_name = cursor.spelling
    return (struct_name, typedef_name)
  elif t.kind == TypeKind.RECORD:
    struct_cursor = t.get_declaration()
    struct_name = struct_cursor.spelling
    typedef_name = cursor.spelling
    return (struct_name, typedef_name)
  else:
    return (None, None)

def is_primitive_typedef(cursor):
  if cursor.kind != CursorKind.TYPEDEF_DECL:
    return False
  t = cursor.underlying_typedef_type
  return t.kind in {
    TypeKind.INT,
    TypeKind.UINT,
    TypeKind.SHORT,
    TypeKind.USHORT,
    TypeKind.LONG,
    TypeKind.ULONG,
    TypeKind.CHAR_S,
    TypeKind.CHAR_U,
    TypeKind.VOID,
    TypeKind.POINTER,
    TypeKind.FLOAT,
    TypeKind.DOUBLE,

    TypeKind.POINTER,
    TypeKind.ENUM,
    TypeKind.RECORD,
  }

index = Index.create()
tu = index.parse("test-variable.h", args = [
  "-I/opt/homebrew/opt/freetype/include/freetype2",
  "-I/opt/homebrew/opt/libpng/include/libpng16"
])

for cursor in tu.cursor.get_children():
  print("")
  if cursor.kind.is_declaration():
    print(cursor.spelling, cursor.kind)

  if is_primitive_typedef(cursor):
    name = cursor.spelling
    t = cursor.underlying_typedef_type.spelling
    print(f"typedef {t} {name};")

  elif is_struct_pointer_typedef(cursor):
    struct_name, typedef_name = get_struct_typedef(cursor)
    if struct_name is not None and typedef_name is not None:
      print(f"typedef struct {struct_name} {typedef_name};")
    else:
      print("/* cannot resolve this type */")
