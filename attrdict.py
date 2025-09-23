#!/usr/bin/env python

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
