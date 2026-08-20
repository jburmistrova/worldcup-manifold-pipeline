"""Lint-only check for the Databricks bundle, run in CI with no workspace
credentials (see .github/workflows/ci-databricks.yml and ADR-0015/0016 for
why a real `databricks bundle validate` isn't wired in here: it genuinely
requires live auth, confirmed empirically -- `databricks bundle validate`
against this exact bundle with every credential env var unset fails with
"cannot configure default credentials", it doesn't fall back to a
credential-free dry-run).

What this actually checks, and what it explicitly does NOT:
- YAML syntax of databricks.yml + resources/*.yml (catches typos, bad
  indentation -- does NOT catch schema errors like an unknown resource key,
  which only surfaces on `bundle validate`).
- Python syntax of every notebook (`py_compile` -- does NOT catch the real
  notebook-cell-structure bug ADR-0015 documents, a %md magic block
  swallowing following code with no `# COMMAND ----------` separator: that
  bug produces syntactically valid Python to a plain compiler, it only
  breaks under Databricks' own notebook-source parser. This class of bug is
  a real, named gap in what this lint can catch, not hidden.).
- Every SQL transformation file starts with `CREATE OR REFRESH` and
  contains no legacy DLT syntax (`import dlt`, `LIVE.`, `CREATE LIVE TABLE`,
  `apply_changes`) -- a direct encoding of the modern-vs-legacy SDP syntax
  table Databricks' own tooling flags, not a full SQL parse (DLT's
  CONSTRAINT/EXPECT syntax is a Databricks-specific DDL extension no
  general-purpose SQL parser -- sqlglot included -- fully supports, so a
  real parse was rejected as producing false failures on correct DLT SQL,
  not attempted here).
"""
import pathlib
import py_compile
import sys

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATABRICKS_DIR = REPO_ROOT / "databricks"

LEGACY_DLT_MARKERS = [
    "import dlt",
    "@dlt.",
    "LIVE.",
    "CREATE LIVE TABLE",
    "CREATE STREAMING LIVE TABLE",
    "CREATE TEMPORARY LIVE VIEW",
    "APPLY CHANGES INTO",
    "apply_changes(",
]


def check_yaml_files():
    errors = []
    yaml_files = [DATABRICKS_DIR / "databricks.yml"] + sorted((DATABRICKS_DIR / "resources").glob("*.yml"))
    for f in yaml_files:
        try:
            yaml.safe_load(f.read_text())
            print(f"  OK  {f.relative_to(REPO_ROOT)}")
        except yaml.YAMLError as e:
            errors.append(f"{f.relative_to(REPO_ROOT)}: {e}")
    return errors


def check_notebook_syntax():
    errors = []
    for f in sorted((DATABRICKS_DIR / "src" / "notebooks").glob("*.py")):
        try:
            py_compile.compile(str(f), doraise=True)
            print(f"  OK  {f.relative_to(REPO_ROOT)}")
        except py_compile.PyCompileError as e:
            errors.append(f"{f.relative_to(REPO_ROOT)}: {e}")
    return errors


def check_sql_files():
    errors = []
    sql_files = sorted((DATABRICKS_DIR / "src" / "pipelines").rglob("*.sql"))
    for f in sql_files:
        text = f.read_text()
        stripped = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("--")
        ).strip()
        if not stripped.upper().startswith("CREATE OR REFRESH"):
            errors.append(f"{f.relative_to(REPO_ROOT)}: doesn't start with CREATE OR REFRESH")
        for marker in LEGACY_DLT_MARKERS:
            if marker in text:
                errors.append(f"{f.relative_to(REPO_ROOT)}: contains legacy DLT syntax {marker!r}")
        if text.count("(") != text.count(")"):
            errors.append(f"{f.relative_to(REPO_ROOT)}: unbalanced parentheses")
        print(f"  OK  {f.relative_to(REPO_ROOT)}")
    return errors


def main():
    all_errors = []

    print("== YAML: databricks.yml + resources/*.yml ==")
    all_errors += check_yaml_files()

    print("\n== Python syntax: src/notebooks/*.py ==")
    all_errors += check_notebook_syntax()

    print("\n== SQL: src/pipelines/**/*.sql ==")
    all_errors += check_sql_files()

    if all_errors:
        print("\nFAILED:")
        for e in all_errors:
            print(f"  - {e}")
        sys.exit(1)

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
