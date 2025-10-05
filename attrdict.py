from types import MappingProxyType
from my_freezer import freeze

class AttrDict:
  def __init__(self, d = None, frozen = False):
    object.__setattr__(self, "_data", dict(d) if d is not None else {})
    object.__setattr__(self, "_frozen", frozen)

  def __getattr__(self, k):
    return self._data.get(k, None)

  def __setattr__(self, k, v):
    if self._frozen:
      raise TypeError("This AttrDict is frozen and cannot be modified.")
    elif k in ("_data", "_frozen"):
      object.__setattr__(self, k, v)
    else:
      self._data[k] = v

  def keys(self):
    return self._data.keys()

  def get_frozen(self):
    return AttrDict(MappingProxyType(self.get_sealed()), frozen = True)

  def get_sealed(self):
    return {
      k: freeze(v)
      for k, v in self._data.items()
    }
