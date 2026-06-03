import os

import django
from django.test.utils import (
    setup_databases,
    setup_test_environment,
    teardown_databases,
    teardown_test_environment,
)


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "trip_planner_backend.settings")
os.environ.setdefault("TRIP_PLANNER_INLINE_JOBS", "false")
django.setup()


def pytest_sessionstart(session):
    setup_test_environment()
    session.config._django_db_config = setup_databases(
        verbosity=0,
        interactive=False,
        keepdb=False,
    )


def pytest_sessionfinish(session, exitstatus):
    old_config = getattr(session.config, "_django_db_config", None)
    if old_config is not None:
        teardown_databases(old_config, verbosity=0)
    teardown_test_environment()
