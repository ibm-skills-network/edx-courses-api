"""
Check the edx-platform stand-ins in mock_apps against the real edx-platform source.

The views are tested against the stand-ins. A stand-in that has drifted from the
platform lets a test pass while the real call fails. So for every function and
method a stand-in defines, this checks the real module still has it and that it
takes the same parameters in the same order.

The real source is read with ``ast`` and never imported. Importing it would need
the whole Open edX dependency tree. ``make test`` checks out the release's source
and sets EDX_PLATFORM_ROOT.

Only modules under edx-platform's own top-level packages are checked. Stand-ins
for other packages (lti_consumer, user_tasks and the like) are not. Names that
start with an underscore or are all capitals belong to the stand-in itself and
are not checked either.

A stand-in whose signature differs between releases defines each version under
``if RELEASE == '<release>':``. Only the block for the release under test is
checked. Django 4.2 means Redwood and Django 5.2 means Verawood, the same rule
the stand-ins use.
"""
import ast
import functools
import os
from pathlib import Path

import django
import pytest

MOCK_APPS = Path(__file__).resolve().parent.parent / 'mock_apps'
PLATFORM_PACKAGES = ('cms', 'common', 'lms', 'openedx', 'xmodule')
RELEASE = 'redwood' if django.VERSION < (5,) else 'verawood'


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
    base = _platform_root().joinpath(*module.split('.'))
    for candidate in (base.with_suffix('.py'), base / '__init__.py'):
        if candidate.is_file():
            return _parse(str(candidate))
    pytest.fail(f'{module} is not in edx-platform at {_platform_root()}')


def _params(func):
    """Parameter names in order, without self or cls."""
    names = [a.arg for a in func.args.posonlyargs + func.args.args]
    if names and names[0] in ('self', 'cls'):
        names = names[1:]
    names += [a.arg for a in func.args.kwonlyargs]
    return names


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


def _stub_names(body):
    defs = {name: node for name, node in _defs(body).items() if _public(name)}
    assigned = {
        t.id for n in body if isinstance(n, ast.Assign) for t in n.targets
        if isinstance(t, ast.Name) and _public(t.id)
    }
    return defs, assigned


def _cases():
    for path in sorted(MOCK_APPS.rglob('*.py')):
        module = _module_name(path)
        if module.split('.')[0] not in PLATFORM_PACKAGES:
            continue
        defs, assigned = _stub_names(_stub_body(_parse(str(path))))
        for name in sorted(set(defs) | assigned):
            yield pytest.param(module, name, id=f'{module}.{name}')


def _check(stub, real, where):
    if isinstance(stub, (ast.FunctionDef, ast.AsyncFunctionDef)):
        assert isinstance(real, (ast.FunctionDef, ast.AsyncFunctionDef)), f'{where} is not a function in edx-platform'
        assert _params(stub) == _params(real), f'{where} takes {_params(real)} in edx-platform'
    elif isinstance(stub, ast.ClassDef):
        assert isinstance(real, ast.ClassDef), f'{where} is not a class in edx-platform'
        real_defs = _defs(real.body)
        for name, member in _defs(stub.body).items():
            # A model's DoesNotExist comes from Django, not from the class body.
            if name == 'DoesNotExist' or not _public(name):
                continue
            assert name in real_defs, f'{where}.{name} is not defined on the class in edx-platform'
            _check(member, real_defs[name], f'{where}.{name}')


@pytest.mark.parametrize('module, name', list(_cases()))
def test_stand_in_matches_edx_platform(module, name):
    stub_path = next(p for p in MOCK_APPS.rglob('*.py') if _module_name(p) == module)
    stub_defs, _ = _stub_names(_stub_body(_parse(str(stub_path))))
    real_tree = _real_module(module)
    real_defs = _defs(real_tree.body)
    stub_def = stub_defs.get(name)
    if stub_def is None:
        assert name in real_defs or name in _bound_names(real_tree.body), f'{module} has no {name} in edx-platform'
        return
    if name not in real_defs:
        # Bound by an import or assignment in the real module, so only the name can be checked.
        assert name in _bound_names(real_tree.body), f'{module} has no {name} in edx-platform'
        return
    _check(stub_def, real_defs[name], f'{module}.{name}')
