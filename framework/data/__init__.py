"""
Package : framework.data
Author  : Anil Kalisetti
Purpose : Data-validation library for ETL / migration / reconciliation testing.
"""

from framework.data.etl_validator import CheckResult, ETLValidator

__all__ = ["CheckResult", "ETLValidator"]
