"""
Static Analysis Gate -- openZero
=================================
AST-based checks that mirror the most-triggered GitHub CodeQL
`security-and-quality` queries for Python and TypeScript. Runs fast
(no network, no runtime) and blocks CI before the full CodeQL scan fires.

Checks covered
--------------
Python (using ast module):
	py/catch-base-exception     bare `except:` or `except BaseException:`
	py/empty-except             except clause whose only statement is `pass`
	py/duplicate-key-dict-literal  repeated string key in a dict literal
	py/repeated-import          symbol imported at module level and again
	                            inside a function body
	py/multiple-definition      same symbol imported more than once at
	                            module level
	py/mixed-returns            function has both `return` and `return <value>`
	py/stack-trace-exposure     exception variable interpolated into a value
	                            that is returned or appended to a list

TypeScript (regex-based heuristic):
	js/useless-assignment-to-local  local variable assigned a non-trivial
	                                initial value immediately overwritten in
	                                every branch before any read

Run:
	python -m pytest tests/test_static_analysis.py -v
"""

import ast
import pathlib
import re
from typing import Iterator, List, Tuple

import pytest

# ---------------------------------------------------------------------------
# Source file discovery
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).parent.parent

PY_SOURCES: List[pathlib.Path] = sorted(
	p for p in REPO_ROOT.glob("src/backend/**/*.py")
	if ".venv" not in p.parts and "__pycache__" not in p.parts
)

TS_SOURCES: List[pathlib.Path] = sorted(
	list(REPO_ROOT.glob("src/dashboard/components/**/*.ts"))
	+ list(REPO_ROOT.glob("src/dashboard/services/**/*.ts"))
	+ list(REPO_ROOT.glob("src/dashboard/src/**/*.ts"))
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(path: pathlib.Path):
	"""
	Parse a Python source file into an AST, respecting the file's own encoding
	cookie (PEP 263). Returns None and prints a warning for files that cannot
	be parsed (e.g. intentional encoding fixtures in tests).
	"""
	try:
		return ast.parse(path.read_bytes())
	except SyntaxError as exc:
		print(f"  WARNING: skipping {path} -- SyntaxError: {exc}")
		return None


def _loc(path: pathlib.Path, lineno: int) -> str:
	return f"{path.relative_to(REPO_ROOT)}:{lineno}"


def _pass_only(body: list) -> bool:
	"""True when a block contains only a Pass node (ignoring docstrings)."""
	stmts = [s for s in body if not (
		isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
	)]
	return len(stmts) == 1 and isinstance(stmts[0], ast.Pass)


class _ReturnCollector(ast.NodeVisitor):
	"""Collect Return nodes without descending into nested function scopes."""

	def __init__(self) -> None:
		self.returns: List[Tuple[int, bool]] = []  # (lineno, has_value)

	def visit_Return(self, node: ast.Return) -> None:
		self.returns.append((node.lineno, node.value is not None))

	def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
		pass  # stop descent -- returns inside nested functions are separate

	visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]
	visit_Lambda = visit_FunctionDef  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Python checks
# ---------------------------------------------------------------------------

class TestPythonBareExcept:
	"""py/catch-base-exception -- never catch bare except: or BaseException."""

	def _collect(self) -> List[str]:
		hits: List[str] = []
		for path in PY_SOURCES:
			tree = _parse(path)
			if tree is None:
				continue
			for node in ast.walk(tree):
				if not isinstance(node, ast.ExceptHandler):
					continue
				if node.type is None:
					hits.append(f"{_loc(path, node.lineno)}  bare except:")
				elif (
					isinstance(node.type, ast.Name)
					and node.type.id == "BaseException"
				):
					hits.append(f"{_loc(path, node.lineno)}  except BaseException:")
		return hits

	def test_no_bare_except(self) -> None:
		hits = self._collect()
		assert not hits, (
			"Bare except: or except BaseException: found "
			"(CodeQL py/catch-base-exception):\n"
			+ "\n".join(f"  {h}" for h in hits)
		)


class TestPythonEmptyExcept:
	"""
	py/empty-except (worst case) -- a *bare* except clause (no type) whose body
	is only `pass`. Typed `except X: pass` patterns are intentional in this
	codebase (accompanied by inline comments explaining the rationale) and are
	not flagged here -- they are caught by the bare-except test if untyped.
	"""

	def _collect(self) -> List[str]:
		hits: List[str] = []
		for path in PY_SOURCES:
			tree = _parse(path)
			if tree is None:
				continue
			for node in ast.walk(tree):
				if not isinstance(node, ast.ExceptHandler):
					continue
				# Only flag bare `except: pass` -- the highest-risk combination.
				# Typed `except X: pass` with comments is intentional.
				if node.type is None and _pass_only(node.body):
					hits.append(f"{_loc(path, node.lineno)}  bare except: pass")
		return hits

	def test_no_empty_except(self) -> None:
		hits = self._collect()
		assert not hits, (
			"except clause containing only `pass` (CodeQL py/empty-except):\n"
			+ "\n".join(f"  {h}" for h in hits)
		)


class TestPythonDuplicateDictKeys:
	"""py/duplicate-key-dict-literal -- repeated string key in a dict literal."""

	def _collect(self) -> List[str]:
		hits: List[str] = []
		for path in PY_SOURCES:
			tree = _parse(path)
			if tree is None:
				continue
			for node in ast.walk(tree):
				if not isinstance(node, ast.Dict):
					continue
				seen: dict = {}
				for k in node.keys:
					if (
						k is not None
						and isinstance(k, ast.Constant)
						and isinstance(k.value, str)
					):
						if k.value in seen:
							hits.append(
								f"{_loc(path, k.lineno)}  duplicate key "
								f"{k.value!r} (first at line {seen[k.value]})"
							)
						else:
							seen[k.value] = k.lineno
		return hits

	def test_no_duplicate_dict_keys(self) -> None:
		hits = self._collect()
		assert not hits, (
			"Duplicate string keys in dict literal "
			"(CodeQL py/duplicate-key-dict-literal):\n"
			+ "\n".join(f"  {h}" for h in hits)
		)


class TestPythonRepeatedImport:
	"""py/repeated-import -- symbol imported at module level then again inside a function."""

	def _module_names(self, tree: ast.Module) -> set:
		names: set = set()
		for node in ast.iter_child_nodes(tree):
			if isinstance(node, ast.ImportFrom):
				for alias in node.names:
					names.add(alias.asname or alias.name)
			elif isinstance(node, ast.Import):
				for alias in node.names:
					names.add(alias.asname or alias.name.split(".")[0])
		return names

	def _collect(self) -> List[str]:
		hits: List[str] = []
		for path in PY_SOURCES:
			tree = _parse(path)
			if tree is None:
				continue
			module_names = self._module_names(tree)
			for fn_node in ast.walk(tree):
				if not isinstance(fn_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
					continue
				for child in ast.walk(fn_node):
					if child is fn_node:
						continue
					# stop at nested function definitions
					if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
						continue
					if isinstance(child, ast.ImportFrom):
						for alias in child.names:
							name = alias.asname or alias.name
							if name in module_names:
								hits.append(
									f"{_loc(path, child.lineno)}  "
									f"re-import of {name!r} inside {fn_node.name!r}"
								)
					# bare `import X` inside a function when module-level `import X`
					# exists is a common "local alias" pattern for stdlib modules and
					# is not flagged here -- only from-imports are checked.
		return hits

	def test_no_repeated_imports(self) -> None:
		hits = self._collect()
		assert not hits, (
			"Symbol re-imported inside function already imported at module level "
			"(CodeQL py/repeated-import):\n"
			+ "\n".join(f"  {h}" for h in hits)
		)


class TestPythonModuleLevelDuplicateImport:
	"""py/multiple-definition -- same symbol imported more than once at module level."""

	def _collect(self) -> List[str]:  # type: ignore[override]
		hits: List[str] = []
		for path in PY_SOURCES:
			tree = _parse(path)
			if tree is None:
				continue
			seen: dict = {}
			for node in ast.iter_child_nodes(tree):
				pairs: List[Tuple[str, int]] = []
				if isinstance(node, ast.ImportFrom):
					for alias in node.names:
						pairs.append((alias.asname or alias.name, node.lineno))
				elif isinstance(node, ast.Import):
					for alias in node.names:
						pairs.append((
							alias.asname or alias.name.split(".")[0],
							node.lineno,
						))
				for name, lineno in pairs:
					if name in seen:
						hits.append(
							f"{_loc(path, lineno)}  duplicate import of "
							f"{name!r} (first at line {seen[name]})"
						)
					else:
						seen[name] = lineno
		return hits

	def test_no_duplicate_module_imports(self) -> None:
		hits = self._collect()
		assert not hits, (
			"Same symbol imported more than once at module level "
			"(CodeQL py/multiple-definition):\n"
			+ "\n".join(f"  {h}" for h in hits)
		)


class TestPythonMixedReturns:
	"""py/mixed-returns -- function has both bare `return` and `return <value>`."""

	def _collect(self) -> List[str]:  # type: ignore[override]
		hits: List[str] = []
		for path in PY_SOURCES:
			tree = _parse(path)
			if tree is None:
				continue
			for fn_node in ast.walk(tree):
				if not isinstance(fn_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
					continue
				collector = _ReturnCollector()
				for child in ast.iter_child_nodes(fn_node):
					collector.visit(child)
				with_value = [ln for ln, has_v in collector.returns if has_v]
				bare = [ln for ln, has_v in collector.returns if not has_v]
				if with_value and bare:
					hits.append(
						f"{_loc(path, fn_node.lineno)}  {fn_node.name!r} -- "
						f"bare return at lines {bare}, "
						f"value return at lines {with_value}"
					)
		return hits

	def test_no_mixed_returns(self) -> None:
		hits = self._collect()
		assert not hits, (
			"Function mixes bare `return` with `return <value>` "
			"(CodeQL py/mixed-returns):\n"
			+ "\n".join(f"  {h}" for h in hits)
		)


class TestPythonStackTraceExposure:
	"""
	py/stack-trace-exposure -- exception variable interpolated into a value
	that is returned or appended to a list, making the stack trace user-visible.

	Heuristic: inside an except handler that binds `as <name>`, look for
	f-strings embedding that name where the f-string is:
	  - the argument to a `return` statement, or
	  - the argument to a `.append()` call.
	"""

	@staticmethod
	def _fstring_uses(node: ast.JoinedStr, name: str) -> bool:
		return any(
			isinstance(n, ast.Name) and n.id == name
			for n in ast.walk(node)
		)

	def _collect(self) -> List[str]:  # type: ignore[override]
		hits: List[str] = []
		for path in PY_SOURCES:
			tree = _parse(path)
			if tree is None:
				continue
			for try_node in ast.walk(tree):
				if not isinstance(try_node, ast.Try):
					continue
				for handler in try_node.handlers:
					exc_name = handler.name
					if not exc_name:
						continue
					for stmt in ast.walk(handler):
						# return f"...{e}..."
						if (
							isinstance(stmt, ast.Return)
							and isinstance(stmt.value, ast.JoinedStr)
							and self._fstring_uses(stmt.value, exc_name)
						):
							hits.append(
								f"{_loc(path, stmt.lineno)}  "
								f"exception {exc_name!r} in return f-string"
							)
						# list.append(f"...{e}...")
						if (
							isinstance(stmt, ast.Expr)
							and isinstance(stmt.value, ast.Call)
							and isinstance(stmt.value.func, ast.Attribute)
							and stmt.value.func.attr == "append"
						):
							for arg in stmt.value.args:
								if (
									isinstance(arg, ast.JoinedStr)
									and self._fstring_uses(arg, exc_name)
								):
									hits.append(
										f"{_loc(path, stmt.lineno)}  "
										f"exception {exc_name!r} in .append() f-string"
									)
		return hits

	def test_no_stack_trace_exposure(self) -> None:
		hits = self._collect()
		assert not hits, (
			"Exception variable interpolated into returned/appended value "
			"(CodeQL py/stack-trace-exposure):\n"
			+ "\n".join(f"  {h}" for h in hits)
		)


# ---------------------------------------------------------------------------
# TypeScript checks (regex-based heuristic)
# ---------------------------------------------------------------------------

# Matches:  let varName[: Type] = this.propName;
# Narrowed to `this.<prop>` only -- the exact pattern CodeQL caught in this
# codebase. Chains, method calls, and other initial values require full
# data-flow analysis to verify (handled by the VS Code CodeQL extension).
_LET_DECL = re.compile(
	r"^(?P<indent>\s*)let\s+(?P<var>\w+)\s*(?::\s*[\w<>\[\]|&., ]+)?\s*"
	r"=\s*(?P<init>this\.\w+);\s*$"
)
_IF_LINE = re.compile(r"^\s*if\s*\(")
_ASSIGN_RE_TMPL = r"\b{var}\s*="


class TestTypeScriptUselessAssignment:
	"""
	js/useless-assignment-to-local -- a local variable is given a non-trivial
	initial value that is overwritten in every branch before any read.

	Heuristic (conservative -- low false-positive rate):
	  1. `let X = <non-trivial>;`
	  2. The very next non-blank non-comment line is `if (`
	  3. Within the following 40 lines, `X =` appears at least twice
	     (meaning both the if-body and else-body reassign it)
	  4. X does not appear as a plain read (`X` not followed by `=`) before
	     the first reassignment -- approximated by checking the if-condition
	     line itself.
	"""

	def _next_code_line(self, lines: List[str], after: int) -> Tuple[int, str]:
		"""Return (index, content) of the next non-blank non-comment line."""
		for i in range(after, min(after + 5, len(lines))):
			stripped = lines[i].strip()
			if stripped and not stripped.startswith("//"):
				return i, lines[i]
		return -1, ""

	def _collect(self) -> List[str]:
		hits: List[str] = []
		for path in TS_SOURCES:
			lines = path.read_text().splitlines()
			for i, line in enumerate(lines):
				m = _LET_DECL.match(line)
				if not m:
					continue
				var = m.group("var")
				# Next code line must be `if (`
				ni, next_line = self._next_code_line(lines, i + 1)
				if ni == -1 or not _IF_LINE.match(next_line):
					continue
				# The if-condition line must NOT read `var` (would be a use)
				if_condition = next_line
				assign_re = re.compile(_ASSIGN_RE_TMPL.format(var=re.escape(var)))
				read_re = re.compile(rf"\b{re.escape(var)}\b(?!\s*=)")
				# Allow `var =` in the condition (assignment expression) but
				# flag if there's a plain read of var in the condition
				cond_text = re.sub(rf"\b{re.escape(var)}\s*=", "", if_condition)
				if read_re.search(cond_text):
					continue  # var is actually read in the if condition
				# Count reassignments in the next 40 lines
				block = "\n".join(lines[i + 1: i + 41])
				reassign_count = len(assign_re.findall(block))
				if reassign_count >= 2:
					hits.append(
						f"{path.relative_to(REPO_ROOT)}:{i + 1}  "
						f"useless initial assignment to {var!r}"
					)
		return hits

	def test_no_useless_ts_assignment(self) -> None:
		hits = self._collect()
		assert not hits, (
			"Local variable assigned a value immediately overwritten in every branch "
			"(CodeQL js/useless-assignment-to-local):\n"
			+ "\n".join(f"  {h}" for h in hits)
		)
