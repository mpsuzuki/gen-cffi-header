import re
from types import MappingProxyType
from pathlib import Path
from clang.cindex import Index, CursorKind, TokenKind, TypeKind, TranslationUnit

from attrdict import AttrDict

regex_angle_bracketed_at_end = re.compile(r"<[^<>\s]+>\s*$")

def ends_with_angle_bracketed(str):
  return bool(regex_angle_bracketed_at_end.search(str))


def extent_as_string(extent, full_path = True):
  x0 = extent.start
  x1 = extent.end
  if x0.file is None:
    b = "<NONE>"
  elif full_path:
    b = x0.file.name
  else:
    b = Path(x0.file.name).name

  if x0.line != x1.line:
    return (
      f"{b}:{x0.line}:{x0.column}.."
      f"{x1.line}:{x1.column}"
    )
  else:
    return (
      f"{b}:{x0.line}:"
      f"{x0.column}..{x1.column}"
    )

class ClangASTWalker:
  def __init__(self):
    self._dic_pls = dict()
    self._dic_token_identifier = dict()


  def append_file_to_dict_pls(self, path):
    dic_pls = self._dic_pls
    dic_pls[path] = dict()

    with open(path, "r") as fh:
      lines = fh.read().splitlines()

    for i, str in enumerate(lines, start = 1):
      dic_pls[path][i] = str


  def update_dict_path_line_string(self, ast):
    for h in ast.get_includes():
      self.append_file_to_dict_pls(h.include.name)


  def get_string_from_path_line(self, path, line):
    dic_pls = self._dic_pls
    if path in dic_pls and line in dic_pls[path]:
      return dic_pls[path][line]
    return None


  def get_string_from_extent(self, extent):
    x0 = extent.start
    x1 = extent.end
    if x0.file is None or x0.file.name is None:
      return "<extent.start.file is None>"

    s0 = self.get_string_from_path_line(x0.file.name, x0.line)
    if s0 is None:
      return f"<cannot get string for {x0.file.name}:{x0.line}>"
    elif x0.line == x1.line:
      return s0[(x0.column - 1):(x1.column - 1)]
    else:
      s1 = self.get_string_from_path_line(x1.file.name, x1.line)
      return " ... ".join([
        s0[(x0.column - 1):],
        s1[:(x1.column - 1)].split()[-1]
      ])


  def dump_tokens(self, cursor, indent = ""):
    dic_token_identifier = self._dic_token_identifier
    for t in cursor.translation_unit.get_tokens(extent = cursor.extent):
      token_line_first = t.spelling.split()[0]
      print(f"{indent}  {t.kind} {token_line_first}")
    print("")


  def is_macro_defines_to_angle_bracketed(self, cursor):
    if cursor.kind != CursorKind.MACRO_DEFINITION:
      return False

    x = self.get_string_from_extent(cursor.extent)
    return ends_with_angle_bracketed(x)

  def get_angle_bracketed_from_cursor(self, cursor):
    s = self.get_string_from_extent(cursor.extent)
    m = regex_angle_bracketed_at_end.search(s)
    if m is None:
      return None
    else:
      return m.group()


  def walk(self, cursor, indent = "", verbose = False):
    dic_token_identifier = self._dic_token_identifier
    if verbose:
      # print(f"{indent}{str(cursor.kind)} \'{get_string_from_extent(cursor.extent)}\'")
      print(f"{indent}{str(cursor.kind)} \'{cursor.spelling}\' in "
            f"\'{self.get_string_from_extent(cursor.extent)}\'")
            # f"\'{extent_as_string(cursor.extent, False)}\'")
    # preprocessor does not deal <...> as single token, but we do for FreeType2.
    if self.is_macro_defines_to_angle_bracketed(cursor):
      if verbose:
        dst = self.get_angle_bracketed_from_cursor(cursor)
        print(f"{indent}  {cursor.spelling} -> {dst}")
      return

    if verbose:
      self.dump_tokens(cursor, indent)

    child_cursors = list(cursor.get_children())
    for t in cursor.translation_unit.get_tokens(extent = cursor.extent):
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
    #if len(child_cursors) == 0:
    #  self.dump_tokens(cursor, indent)

    for c in child_cursors:
      self.walk(c, indent = (indent + "    "), verbose = verbose)

  def get_identifier_dict(self):
    return MappingProxyType({
      k: v.get_sealed() # should we test v is AttrDict() ?
      for k, v in self._dic_token_identifier.items()
    })

  def dump_dict(self):
    dic_token_identifier = self._dic_token_identifier
    # for idfr, ad in dic_token_identifier.items():
    for idfr in sorted(dic_token_identifier.keys()):
      print(idfr)
      ad = dic_token_identifier[idfr]
      for c, t in zip(ad.cursors, ad.tokens):
        ck = c.kind
        x = t.extent
        sx = extent_as_string(x, False)
        l = self.get_string_from_path_line(x.start.file.name, x.start.line)
        print(f"  {ck} {sx} \'{l}\'")

  def install_ast(self, header_ast, indent = "", verbose = False):
    self.update_dict_path_line_string(header_ast)
    self.walk(header_ast.cursor, indent, verbose)
    return self
