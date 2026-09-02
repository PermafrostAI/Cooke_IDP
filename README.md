# Cooke_IDP

## Pre-commits

### Step 1: Set up a virtual environment

A virtual environment keeps the tools for this project separate from your
system Python. Pick one of the two approaches below.

#### Option A: Python native venv

```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install pre-commit
```

#### Option B: uv (recommended)

uv is faster than pip and handles both the environment and package installs
in one tool. Install it if you do not have it:

```bash
curl -Ls https://astral.sh/uv/install.sh | sh
```

Create and activate the environment, then install pre-commit:

```bash
uv venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
uv pip install pre-commit
```

This project current consists of the following pre-commit hooks, all defined in `.pre-commit-config.yaml`.

| Hook | Auto-fixes | Flags only |
|---|---|---|
| `sqlfluff-fix` | Casing, indentation, trailing whitespace | `SELECT *`, unfixable rules |
| `sqlfluff-lint` | - | Any remaining SQL violations after fix |
| `isort` | Import ordering in Python files | - |
| `nbstripout` | Strips cell outputs and execution counts | - |
| `nbqa-isort` | Import ordering in notebook cells | - |
| `nbqa-flake8` | - | Unused imports in notebook cells |

> **NOTE:** You need to activate the environment every time you open a new terminal
> session before running any `pre-commit` commands.

### Step 2: Running pre-commits

Run all hooks across all files at once:

```bash
pre-commit run --all-files
```

You will see output from every hook. 