# System Requirements

Prerequisites to run this project — not to be confused with [`requirements.txt`](requirements.txt), which lists Python *packages*. This is what has to be true about the machine before that even matters.

A living doc, updated whenever a new system dependency gets added (e.g. Docker/minikube/kubectl once the Kubernetes phase starts, `dbt-core`/`dbt-duckdb` once the dbt phase starts).

## Runtime versions

| Tool | Version | Why this version |
|---|---|---|
| Python | **3.14.6** | Latest stable release. Confirmed compatible with both major dependencies before switching: PySpark 4.2.0 requires `>=3.10` (no upper cap) [1], dbt Core 1.12 officially supports 3.10 through 3.14 [2]. The project started on the system's pre-installed Python 3.8.10, which is well past end-of-life — Python only supports each minor version for ~5 years after release, and 3.8's window closed in October 2024 [3]. Even 3.9 is EOL now (October 2025), and 3.10 EOLs in ~3 months (October 2026) [3] — using anything less than the current release means picking a version already on a countdown to losing security patches. |
| Java | **OpenJDK 25** (latest LTS) | PySpark 4.2.0 requires Java 17+ [4]. Deliberately picked the latest **LTS** release, not the latest release overall — Java 26 (non-LTS) was released more recently but gets a much shorter support window before Java 27 supersedes it (~2 months away as of this writing); Java 25 gets extended support under Oracle's NFTC terms until September 2028 [5]. "Most stable" for Java specifically means LTS, not bleeding-edge. |

## Installation

Both installed via Homebrew — deliberately avoided a from-source Python build (see "what broke" below) and avoided `sudo`-based system-wide Java symlinking (would affect every project on the machine, not just this one).

```bash
brew install openjdk@25
brew install python@3.14
brew install duckdb
```

`duckdb` (the standalone CLI, separate from the `duckdb` Python package in `requirements.txt`) isn't required to run the pipeline — dbt talks to DuckDB through the Python package. It's for browsing the data directly: `duckdb -ui dbt/manifold.duckdb` opens DuckDB's built-in local web UI (a real DuckDB feature, not a third-party tool) with a schema browser and SQL editor against whatever dbt has built so far. Note it holds an exclusive file lock while open — a second connection (e.g. a script inspecting the same file) needs the UI session closed first, or should query the underlying Parquet files directly instead.

Both formulas are keg-only (Homebrew won't make them the system default automatically) — that's intentional here, not a bug to work around by linking them globally. This project references them by explicit path instead:

- Python: `/usr/local/opt/python@3.14/bin/python3.14` — used directly to create the project's `venv`, never linked as the system `python3`.
- Java: `/usr/local/opt/openjdk@25` — set as `JAVA_HOME` in `.env` (see `.env.example`), not in shell profile, so it's scoped to this project.

```bash
rm -rf venv
/usr/local/opt/python@3.14/bin/python3.14 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # JAVA_HOME is already defaulted; no secrets needed (Manifold's API is public, no auth)
```

## What broke the first time

Worth keeping, not editing away — this is exactly the kind of thing worth being able to explain if asked.

Tried `pyenv install 3.14.6` first (building Python from source). Failed twice with the same linker error: `Undefined symbols for architecture arm64: "_libintl_bindtextdomain"` etc. — the build couldn't find `gettext`/`libintl`, which is installed via Homebrew but keg-only. Setting `LDFLAGS`/`CPPFLAGS` to point at it fixed most of the build but not the specific early-bootstrap step (`Programs/_freeze_module`) that failed — a known limitation where `python-build`'s bootstrap compile doesn't fully inherit those environment variables. Rather than keep fighting a source compile, switched to Homebrew's precompiled `python@3.14` formula instead, which sidesteps the whole class of problem — no compilation, no linker issues. `pyenv` is still installed and still useful for other projects; it just isn't what's managing Python for this one.

## Python packages actually in use

`requests`, `pyspark==4.2.0`, `dbt-core==1.12.0`, `dbt-duckdb==1.10.1` — all pinned in [requirements.txt](requirements.txt). Installed the latest of each, confirmed compatible with the Python version above before installing (dbt Core 1.12 officially supports Python 3.10–3.14 [2]; PySpark 4.2.0 requires `>=3.10` with no upper cap [1]).

## Kubernetes tooling

| Tool | Version | Why |
|---|---|---|
| Docker Desktop | 4.84.0 (arm64) | Container runtime, and what `docker build`/`docker run` talk to. Chosen over Colima specifically for resume/interview legibility — the `docker` CLI experience is identical either way (Colima just swaps the backend daemon), but "Docker Desktop" is the name every interviewer recognizes on sight; Colima reads as an insider's substitute that only lands with someone already deep in the weeds. |
| minikube | 1.38.1 | Local single-node Kubernetes cluster. Chosen over `kind` for the same reason: it's the tool featured in Kubernetes' own official "Learn Kubernetes Basics" tutorial, the most broadly recognized name for "I've run a local cluster." `kind` is the more specialized choice — what the Kubernetes project itself uses for CI and operator testing — which reads better to a platform-team specialist but doesn't carry the same broad recognition. |
| kubectl | 1.36.3 | The Kubernetes CLI, installed as a `minikube` dependency. |

```bash
brew install --cask docker
brew install minikube kubectl
minikube start --driver=docker
```

Opening Docker.app once to complete first-run setup (accept its license, install a privileged helper) is GUI-only and can't be scripted — has to happen by hand before `minikube start` will find a working Docker daemon.

## What broke the first time (Kubernetes setup)

This machine has **two parallel Homebrew installations**: a legacy Intel one at `/usr/local` (first on `PATH`) and a native Apple Silicon one at `/opt/homebrew`. Plain `brew install --cask docker` resolved to the Intel `brew`, which silently fetched the x86_64 build of Docker Desktop — no error at install time, since the download and install steps don't check the host architecture against the cask's. It only surfaced when the app actually launched: an immediate crash, `checking compatibility: required compatibility check: This is the Intel version of Docker Desktop`, found in `~/Library/Containers/com.docker.docker/Data/log/host/com.docker.backend.log`.

Fixed by uninstalling the Intel build and reinstalling explicitly through the arm64 Homebrew (`/opt/homebrew/bin/brew install --cask docker`); `minikube` and `kubectl` were installed the same explicit way from the start to sidestep the same bug rather than find it again per tool. `PATH` itself wasn't reordered — same philosophy as pointing at Python/Java by explicit path above rather than trusting what happens to be linked as the default.

## Not yet needed (will be added here when relevant)

None currently — every tool this project uses is listed above.

## References

1. PySpark 4.2.0 PyPI metadata (`requires_python`): https://pypi.org/project/pyspark/
2. dbt Labs. *What version of Python can I use?* https://docs.getdbt.com/faqs/Core/install-python-compatibility
3. Python Developer's Guide. *Status of Python versions.* https://devguide.python.org/versions/ (PEP 619)
4. Apache Spark. *Installation — PySpark documentation.* https://spark.apache.org/docs/latest/api/python/getting_started/install.html
5. Oracle. *Java SE Support Roadmap.* https://www.oracle.com/java/technologies/java-se-support-roadmap.html
