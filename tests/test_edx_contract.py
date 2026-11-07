"""
Check the edx-platform stand-ins in mock_apps against the real edx-platform source.

The views are tested against the stand-ins. A stand-in that has drifted from the
platform lets a test pass while the real call fails. So for every function and
method a stand-in defines, this checks the real module still has it and that it
takes the same parameters in the same order, each of the same kind (positional or
keyword-only) and with the same default. A name a stand-in imports from another
edx-platform module (``grades.api`` importing ``CourseGradeFactory``) has to be bound
in the real module too, because the views import it from there.

The real source is read with ``ast`` and never imported. Importing it would need
the whole Open edX dependency tree. ``make test`` checks out the release's source
and sets EDX_PLATFORM_ROOT.

Only modules under edx-platform's own top-level packages are checked. Stand-ins
for other packages (lti_consumer, user_tasks and the like) are not. Names that
start with an underscore or are all capitals belong to the stand-in itself and
are not checked either.

A stand-in whose signature differs between releases defines each version under
``if RELEASE == '<release>':``. Only the block for the release under test is
checked. test_utils.release says which release is under test.
"""
import ast
import functools
import os
from pathlib import Path

import pytest

from test_utils.release import RELEASE

MOCK_APPS = Path(__file__).resolve().parent.parent / 'mock_apps'
PLATFORM_PACKAGES = ('cms', 'common', 'lms', 'openedx', 'xmodule')


def _platform_root():
    root = os.environ.get('EDX_PLATFORM_ROOT')
    if not root:
        # In CI a missing source tree would turn every case here into a skip.
        if os.environ.get('CI'):
            pytest.fail('EDX_PLATFORM_ROOT is not set. Run `make test`.')
        pytest.skip('EDX_PLATFORM_ROOT is not set. `make test` checks out the edx-platform source.')
    return Path(root)


def _module_name(path):
    parts = path.relative_to(MOCK_APPS).with_suffix('').parts
    return '.'.join(parts[:-1] if parts[-1] == '__init__' else parts)


@functools.lru_cache(maxsize=None)
def _parse(path):
    return ast.parse(Path(path).read_text(), filename=str(path))


def _real_module(module):
    """The parsed real module, and the package its relative imports start from."""
    base = _platform_root().joinpath(*module.split('.'))
    if base.with_suffix('.py').is_file():
        return _parse(str(base.with_suffix('.py'))), module.rpartition('.')[0]
    if (base / '__init__.py').is_file():
        return _parse(str(base / '__init__.py')), module
    pytest.fail(f'{module} is not in edx-platform at {_platform_root()}')


def _find_real(module, name):
    """
    The real definition of name in module, or 'bound' when an import or assignment binds it.

    Follows ``from .x import *``, which is how student.models exposes CourseEnrollment.
    None when the name is not there.
    """
    tree, package = _real_module(module)
    defs = _defs(tree.body)
    if name in defs:
        return defs[name]
    if name in _bound_names(tree.body):
        return 'bound'
    for node in tree.body:
        if (isinstance(node, ast.ImportFrom) and node.level == 1 and node.module
                and any(a.name == '*' for a in node.names)):
            found = _find_real(f'{package}.{node.module}', name)
            if found is not None:
                return found
    return None


def _params(func):
    """
    The parameters in order, without self or cls, as (name, kind, default) tuples.

    The default is its source text, or None for a required parameter. Two
    signatures differ here when a parameter is required in one and optional in
    the other, keyword-only in one, or has a different default.
    """
    args = func.args
    positional = args.posonlyargs + args.args
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    params = [(a.arg, 'positional', d) for a, d in zip(positional, defaults)]
    if params and params[0][0] in ('self', 'cls'):
        params = params[1:]
    if args.vararg:
        params.append((args.vararg.arg, 'var-positional', None))
    params += [(a.arg, 'keyword-only', d) for a, d in zip(args.kwonlyargs, args.kw_defaults)]
    if args.kwarg:
        params.append((args.kwarg.arg, 'var-keyword', None))
    return [(name, kind, None if d is None else ast.unparse(d)) for name, kind, d in params]


def _defs(body):
    return {n.name: n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _bound_names(body):
    """Names a module or class body binds by assignment or import."""
    names = set()
    for node in body:
        if isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split('.')[0] for a in node.names)
    return names


def _is_release_block(node):
    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name) and node.test.left.id == 'RELEASE'
        and isinstance(node.test.ops[0], ast.Eq)
        and isinstance(node.test.comparators[0], ast.Constant)
    )


def _stub_body(tree):
    """The stand-in's top-level statements, with only this release's `if RELEASE ==` blocks kept."""
    body = []
    for node in tree.body:
        while _is_release_block(node):
            if node.test.comparators[0].value == RELEASE:
                body.extend(node.body)
                break
            if len(node.orelse) == 1 and _is_release_block(node.orelse[0]):
                node = node.orelse[0]
                continue
            body.extend(node.orelse)
            break
        else:
            body.append(node)
    return body


def _public(name):
    return not name.startswith('_') and not name.isupper()


def _reexports(body):
    """Names a stand-in imports from an edx-platform module, so the real module has to bind them too."""
    return {
        a.asname or a.name
        for n in body
        if isinstance(n, ast.ImportFrom) and (n.level or (n.module or '').split('.')[0] in PLATFORM_PACKAGES)
        for a in n.names
    }


def _stub_names(body):
    defs = {name: node for name, node in _defs(body).items() if _public(name)}
    bound = {
        t.id for n in body if isinstance(n, ast.Assign) for t in n.targets
        if isinstance(t, ast.Name) and _public(t.id)
    }
    bound |= {name for name in _reexports(body) if _public(name)}
    return defs, bound


def _cases():
    for path in sorted(MOCK_APPS.rglob('*.py')):
        module = _module_name(path)
        if module.split('.')[0] not in PLATFORM_PACKAGES:
            continue
        defs, bound = _stub_names(_stub_body(_parse(str(path))))
        for name in sorted(set(defs) | bound):
            yield pytest.param(module, name, id=f'{module}.{name}')


def _check(stub, real, where):
    if isinstance(stub, (ast.FunctionDef, ast.AsyncFunctionDef)):
        assert isinstance(real, (ast.FunctionDef, ast.AsyncFunctionDef)), f'{where} is not a function in edx-platform'
        assert _params(stub) == _params(real), f'{where} takes {_params(real)} in edx-platform'
    elif isinstance(stub, ast.ClassDef):
        assert isinstance(real, ast.ClassDef), f'{where} is not a class in edx-platform'
        real_defs = _defs(real.body)
        stub_defs = _defs(stub.body)
        # A Django model has no __init__ of its own. It takes its fields as keyword
        # arguments. So when the real class defines no __init__, every parameter of the
        # stand-in's __init__ has to be a name the real class body assigns. Without this
        # a renamed field passes here, and the real constructor raises TypeError.
        init = stub_defs.get('__init__')
        if init is not None and '__init__' not in real_defs:
            fields = _bound_names(real.body)
            for param, kind, _ in _params(init):
                if kind in ('positional', 'keyword-only'):
                    assert param in fields, f'{where} has no field {param} in edx-platform'
        for name, member in stub_defs.items():
            # A model's DoesNotExist comes from Django, not from the class body.
            if name == 'DoesNotExist' or not _public(name):
                continue
            assert name in real_defs, f'{where}.{name} is not defined on the class in edx-platform'
            _check(member, real_defs[name], f'{where}.{name}')


@pytest.mark.parametrize('module, name', list(_cases()))
def test_stand_in_matches_edx_platform(module, name):
    stub_path = next(p for p in MOCK_APPS.rglob('*.py') if _module_name(p) == module)
    stub_defs, _ = _stub_names(_stub_body(_parse(str(stub_path))))
    real = _find_real(module, name)
    assert real is not None, f'{module} has no {name} in edx-platform'
    stub_def = stub_defs.get(name)
    # A name the real module binds by an import or assignment can only be checked by name.
    if stub_def is not None and real != 'bound':
        _check(stub_def, real, f'{module}.{name}')
