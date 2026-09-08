#!/usr/bin/env python3
"""Local CI Runner for Data Engineering Pipelines.

Executes all continuous integration stages locally:
1. Static Code Analysis & Linting (Flake8)
2. Code Style & Formatting Compliance (Black)
3. Unit & Mock Testing Suite with Coverage (Pytest)
4. Schema Contracts & Data Quality Verification
5. End-to-End Pipeline Dry Run

Usage:
    python scripts/run_local_ci.py
"""

import os
import subprocess
import sys
import time
from pathlib import Path

# ANSI colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner(text: str):
    print(f"\n{CYAN}{BOLD}{'=' * 70}{RESET}")
    print(f"{CYAN}{BOLD}  STAGE: {text}{RESET}")
    print(f"{CYAN}{BOLD}{'=' * 70}{RESET}")


def run_command(cmd_list: list, stage_name: str) -> bool:
    print(f"{YELLOW}[>] Executing: {' '.join(cmd_list)}{RESET}")
    start = time.time()
    try:
        res = subprocess.run(cmd_list, capture_output=True, text=True, check=False)
        duration = round(time.time() - start, 2)
        if res.stdout:
            print(res.stdout)
        if res.stderr:
            print(f"{YELLOW}{res.stderr}{RESET}")

        if res.returncode == 0:
            print(f"{GREEN}[PASS] {stage_name} passed in {duration}s{RESET}")
            return True
        else:
            print(f"{RED}[FAIL] {stage_name} failed with exit code {res.returncode} ({duration}s){RESET}")
            return False
    except Exception as e:
        print(f"{RED}[ERROR] Execution failed: {e}{RESET}")
        return False


def main():
    repo_root = Path(__file__).resolve().parents[1]
    os.chdir(repo_root)

    # Determine python / pytest executable path
    venv_python = repo_root / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        venv_python = repo_root / ".venv" / "bin" / "python"
    
    python_bin = str(venv_python) if venv_python.exists() else sys.executable

    print(f"{BOLD}{GREEN}======================================================================{RESET}")
    print(f"{BOLD}{GREEN}           LOCAL DATA ENGINEERING CI/CD RUNNER                        {RESET}")
    print(f"{BOLD}{GREEN}======================================================================{RESET}")
    print(f"Repository Root: {repo_root}")
    print(f"Python Executable: {python_bin}\n")

    stages_results = {}

    # Stage 1: Flake8 Syntax & Critical Linting
    print_banner("1. Static Code Analysis & Linting (Flake8)")
    stages_results["Flake8 Linting"] = run_command(
        [python_bin, "-m", "flake8", "src", "tests", "--count", "--max-line-length=120"],
        "Flake8 Linting",
    )

    # Stage 2: Black Formatting Check
    print_banner("2. Code Style & Formatting Compliance (Black)")
    stages_results["Black Formatting"] = run_command(
        [python_bin, "-m", "black", "--check", "src", "tests"],
        "Black Formatting Check",
    )

    # Stage 3: Pytest Unit & Mock Test Suite with Coverage
    print_banner("3. Unit & Mock Testing Suite with Coverage (Pytest)")
    stages_results["Pytest Unit & Mock Tests"] = run_command(
        [python_bin, "-m", "pytest", "-v", "--cov=src/pipeline", "--cov-report=term-missing", "--cov-fail-under=85"],
        "Pytest Test Suite",
    )

    # Stage 4: End-to-End Pipeline Dry Run
    print_banner("4. End-to-End Data Pipeline Execution")
    stages_results["Pipeline Dry Run"] = run_command(
        [python_bin, "scripts/run_pipeline.py", "--env", "dev"],
        "Pipeline Execution",
    )

    # Summary Report
    print(f"\n{BOLD}{CYAN}{'=' * 70}{RESET}")
    print(f"{BOLD}{CYAN}                     LOCAL CI RUN SUMMARY                            {RESET}")
    print(f"{BOLD}{CYAN}{'=' * 70}{RESET}")

    all_passed = True
    for stage, passed in stages_results.items():
        status_text = f"{GREEN}[PASSED]{RESET}" if passed else f"{RED}[FAILED]{RESET}"
        if not passed:
            all_passed = False
        print(f"  {stage:<40} {status_text}")

    print(f"{BOLD}{CYAN}{'=' * 70}{RESET}")

    if all_passed:
        print(f"{BOLD}{GREEN}ALL CI CHECKS PASSED! Ready for Git Commit / Pull Request.{RESET}\n")
        sys.exit(0)
    else:
        print(f"{BOLD}{RED}CI CHECKS FAILED. Please resolve errors before merging.{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
