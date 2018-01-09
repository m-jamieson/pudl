"""PyTest configuration module. Defines useful fixtures, command line args."""

import pytest
import pandas as pd
import pudl.extract.ferc1
from pudl import init
from pudl import constants as pc


def pytest_addoption(parser):
    """Add a command line option for using the live FERC/PUDL DB."""
    parser.addoption("--live_ferc_db", action="store_true", default=False,
                     help="Use live FERC DB rather than test DB.")
    parser.addoption("--live_pudl_db", action="store_true", default=False,
                     help="Use live PUDL DB rather than test DB.")


@pytest.fixture(scope='session')
def live_ferc_db(request):
    """Fixture that tells use which FERC DB to use (live vs. testing)."""
    return request.config.getoption("--live_ferc_db")


@pytest.fixture(scope='session')
def live_pudl_db(request):
    """Fixture that tells use which PUDL DB to use (live vs. testing)."""
    return request.config.getoption("--live_pudl_db")


@pytest.fixture(scope='session')
def ferc1_engine(live_ferc_db):
    """
    Grab a conneciton to the FERC Form 1 DB clone.

    If we are using the test database, we initialize it from scratch first.
    If we're using the live database, then we just yield a conneciton to it.
    """
    ferc1_tables = pc.ferc1_default_tables
    ferc1_refyear = max(pc.working_years['ferc1'])

    if not live_ferc_db:
        pudl.extract.ferc1.init_db(ferc1_tables=ferc1_tables,
                                   refyear=ferc1_refyear,
                                   years=pc.working_years['ferc1'],
                                   def_db=True,
                                   verbose=True,
                                   testing=True)

        # Grab a connection to the freshly populated database, and hand it off.
        ferc1_engine = pudl.extract.ferc1.db_connect_ferc1(testing=True)
        yield(ferc1_engine)

        # Clean up after ourselves by dropping the test DB tables.
        pudl.extract.ferc1.drop_tables_ferc1(ferc1_engine)
    else:
        print("Constructing FERC1 DB MetaData based on refyear {}".
              format(ferc1_refyear))
        pudl.extract.ferc1.define_db(
            ferc1_refyear, ferc1_tables, pudl.extract.ferc1.ferc1_meta)
        print("Connecting to the live FERC1 database.")
        yield(pudl.extract.ferc1.db_connect_ferc1(testing=False))


@pytest.fixture(scope='session')
def pudl_engine(ferc1_engine, live_pudl_db, live_ferc_db):
    """
    Grab a conneciton to the PUDL Database.

    If we are using the test database, we initialize the PUDL DB from scratch.
    If we're using the live database, then we just make a conneciton to it.
    """
    if not live_pudl_db:
        if live_ferc_db:
            ferc1_testing = False
        else:
            ferc1_testing = True
        init.init_db(ferc1_tables=pc.ferc1_pudl_tables,
                     ferc1_years=pc.working_years['ferc1'],
                     eia923_tables=pc.eia923_pudl_tables,
                     eia923_years=pc.working_years['eia923'],
                     eia860_tables=pc.eia860_pudl_tables,
                     eia860_years=pc.working_years['eia860'],
                     verbose=True,
                     debug=False,
                     pudl_testing=True,
                     ferc1_testing=ferc1_testing)

        # Grab a connection to the freshly populated PUDL DB, and hand it off.
        pudl_engine = init.db_connect_pudl(testing=True)
        yield(pudl_engine)

        # Clean up after ourselves by dropping the test DB tables.
        init.drop_tables_pudl(pudl_engine)
    else:
        print("Connecting to the live PUDL database.")
        yield(init.db_connect_pudl(testing=False))
