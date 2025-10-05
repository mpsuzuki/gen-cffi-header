import re
from pathlib import Path
from clang.cindex import CursorKind, TokenKind, TypeKind
from attrdict import AttrDict

def has_overlap(s1, e1, s2, e2):
  if ((s1 - e2) * (e1 - s2)) < 0:
    return True
  else:
    return False

def columns_overlap(x1, x2):
  return has_overlap(x1.start.column, x1.end.column, x2.start.column, x2.end.column)

def lines_overlap(x1, x2):
  return has_overlap(x1.start.line, x1.end.line, x2.start.line, x2.end.line)

class ExtentWrapper:
  def __init__(self, extent, include_dirs = [], spelling = None, frozen = False):
    object.__setattr__(self, "extent", extent)
    object.__setattr__(self, "spelling", spelling)
    object.__setattr__(self, "include_dirs", [Path(d).resolve() for d in include_dirs])
    object.__setattr__(self, "frozen", frozen)

  def __setattr__(self, k, v):
    if self.frozen:
      raise TypeError(f"This {type(self)} is frozen and cannot be modified.")
    elif k in ("extent", "spelling", "include_dirs", "frozen"):
      object.__setattr__(self, k, v)
    else:
      raise TypeError(f"Cannot set \'{k}\' to {type(self)}")

  @classmethod
  def from_cursor(cls, cursor, include_dirs = []):
    if cursor is None:
      raise TypeError("ExtentWrapper.from_cursor() requires valid Cursor object")
    ew = cls(None, include_dirs = include_dirs, spelling = cursor.spelling)
    ew.extent = AttrDict({})
    ew.extent.start = AttrDict({})
    ew.extent.end = AttrDict({})
    ew.extent.start.file = cursor.location.file
    ew.extent.start.line = cursor.location.line
    ew.extent.start.column = cursor.location.column
    ew.extent.end.file = cursor.location.file
    ew.extent.end.line = cursor.location.line
    ew.extent.end.column = cursor.location.column + len(cursor.spelling)
    return ew

  def is_single_file(self):
    if self.extent.start.file is None or self.extent.end.file is None:
      return False
    elif self.extent.start.file.name != self.extent.end.file.name: # not precise, like a.h -> b.h -> a.h
      return False
    else:
      return True

  def is_single_line(self):
    if not self.is_single_file():
      return False
    elif self.extent.start.line != self.extent.end.line:
      return False
    else:
      return True

  def to_string(self, do_relative = False):
    if not self.is_single_file():
      return None

    file_path = Path(self.extent.start.file.name).resolve()
    file_name = min([
      str(file_path.relative_to(d))
      for d in self.include_dirs
      if file_path.is_relative_to(d)
    ], key = len)

    if self.is_single_line():
      return ( f"{file_name}:{self.extent.start.line}:{self.extent.start.column}"
               f"..{self.extent.end.column}" )
    else:
      return ( f"{file_name}:{self.extent.start.line}:{self.extent.start.column}"
               f"..{self.extent.end.line}:{self.extent.end.column}" )

  def overlaps_with(another):
    if not self.is_single_file() or not another.is_single_file():
      return False

    if self.extent.start.file.name != another.extent.start.file.name:
      return False

    if self.is_single_line() and another.is_single_line():
      return columns_overlap(self, another)
    elif self.is_single_line():
      if self.start.line == another.start.line:
        return bool(another.start.column <= self.end.column)
      elif self.end.line == another.end.line:
        return bool(self.start.column <= another.end.column)
      elif another.end.line < self.start.line:
        return False
      elif self.end.line < another.start.line:
        return False
      else:
        return True
    elif another.is_single_line():
      if self.start.line == another.start.line:
        return bool(self.start.column <= another.end.column)
      elif self.end.line == another.end.line:
        return bool(another.start.column <= self.end.column)
      elif self.end.line < another.start.line:
        return False
      elif another.end.line < self.start.line:
        return False
      else:
        return True
    else:
      return lines_overlap(self, another)
