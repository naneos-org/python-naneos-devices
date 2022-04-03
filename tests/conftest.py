"""
    Dummy conftest.py for partector2.

    If you don't know what this is for, just leave it empty.
    Read more about conftest.py under:
    - https://docs.pytest.org/en/stable/fixture.html
    - https://docs.pytest.org/en/stable/writing_plugins.html
"""

# import pytest

# import pathlib
# import _pytest.pathlib


# resolve_pkg_path_orig = _pytest.pathlib.resolve_package_path

# # we consider all dirs in repo/ to be namespace packages
# rootdir = pathlib.Path(__file__).parent.resolve()
# namespace_pkg_dirs = [str(d) for d in rootdir.iterdir() if d.is_dir()]

# # patched method
# def resolve_package_path(path):
#     # call original lookup
#     result = resolve_pkg_path_orig(path)
#     if result is not None:
#         return result
#     # original lookup failed, check if we are subdir of a namespace package
#     # if yes, return the namespace package we belong to
#     for parent in path.parents:
#         if str(parent) in namespace_pkg_dirs:
#             return parent
#     return None

# # apply patch
# _pytest.pathlib.resolve_package_path = resolve_package_path
