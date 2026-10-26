"""
Package : framework.plugins
Author  : Anil Kalisetti
Purpose : pytest plugins loaded from the root conftest.py (options, evidence, Jira, reporting).

All "collector" plugins run ONLY in the main process. Under pytest-xdist the worker processes
execute tests and stream reports to the main process, which owns Jira and report generation;
this avoids duplicate defects and half-written reports.
"""
