from types import MappingProxyType

def has_freeze_method(obj):
  if not hasattr(obj, "freeze"):
    return False
  elif callable(obj.freeze):
    return True
  else:
    return False

def has_seal_method(obj):
  if not hasattr(obj, "seal"):
    return False
  elif callable(obj.seal):
    return True
  else:
    return False

def has_get_frozen_method(obj):
  if not hasattr(obj, "get_frozen"):
    return False
  elif callable(obj.get_frozen):
    return True
  else:
    return False

def has_seal_method(obj):
  if not hasattr(obj, "seal"):
    return False
  elif callable(obj.seal):
    return True
  else:
    return False

def has_get_sealed_method(obj):
  if not hasattr(obj, "get_sealed"):
    return False
  elif callable(obj.get_sealed):
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
  elif has_get_frozen_method(obj):
    return obj.get_frozen()
  elif has_freeze_method(obj):
    obj.freeze()
    return obj
  elif has_get_sealed_method(obj):
    return obj.get_frozen()
  elif has_seal_method(obj):
    obj.seal()
    return obj
  else:
    return obj
