from types import MappingProxyType

def has_freeze_method(obj):
  if not hasattr(obj, "freeze"):
    return False
  elif callable(obj.freeze):
    return True
  else:
    return False

def freeze(obj):
  if isinstance(obj, dict):
    return MappingProxyType({
      k: freeze(v) for k, v in obj.items()
    })
  elif isinstance(obj, list):
    return tuple(freeze(itm) for itm in obj)
  elif isinstance(obj, set):
    return frozenset(freeze(itm) for itm in obj)
  elif has_freeze_method(obj):
    return obj.freeze()
  else:
    return obj
