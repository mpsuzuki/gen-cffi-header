# gen-cffi-header

A script to generate preprocessed header file for Python cffi module.

## Why needed?

Python has a module CFFI to invoke the functions
provided by shared library, from Python.
To define its interface to Python scripting, CFFI
has cdef() method. But cdef() has many limitations
to process raw header files for C (or C++) environment.

* Preprocessor conditionals (#if, #ifdef) are not supported.
* Preprocessor macro can define a numerical value only.
A string, a function or an empty (define or not-defined) value is unacceptable.
* Inline structure/union/enum declaration in typedef is not supported.
A named structure/union/enum should be defined, then refer it in typedef.

## Dependencies

Author used following packages.

```
cffi==2.0.0
libclang==18.1.1
pkgconfig==1.5.5
pycparser==2.23
```

To use gen-cffi-header.py and load-cffi-cdef.py,

```
pip install cffi libclang
```

would be enough.

## How to use

```
./gen-cffi-header.py `pkg-config --cflags freetype2` test-variable.h > test-variable.py.h
./load-cffi-cdef.py test-variable.py.h
```
