"""Routines specific to cleaning up EPA CEMS hourly data."""

import pandas as pd
import numpy as np
import sqlalchemy as sa
import pudl
import pudl.constants as pc

###############################################################################
###############################################################################
# DATATABLE TRANSFORM FUNCTIONS
###############################################################################
###############################################################################


def fix_up_dates(df, plant_utc_offset):
    """Fix the dates for the CEMS data
    Args:
        df(pandas.DataFrame): A CEMS hourly dataframe for one year-month-state
        plant_utc_offset(pandas.DataFrame): A dataframe of plants' timezones
    Output:
        pandas.DataFrame: The same data, with an op_datetime_utc column added
        and the op_date and op_hour columns removed
    """
    # Convert op_date and op_hour from string and integer to datetime:
    # Note that doing this conversion, rather than reading the CSV with
    # `parse_dates=True`, is >10x faster.
    df["op_datetime_naive"] = (
        # Read the date as a datetime, so all the dates are midnight
        # Mark as UTC (it's not true yet, but it will be once we add
        # utc_offsets, and it's easier to do here)
        pd.to_datetime(
            df["op_date"], format=r"%m-%d-%Y", exact=True, cache=True, utc=True
        )
        +
        # Add the hour
        pd.to_timedelta(df["op_hour"], unit="h", box=False)
    )
    df = df.merge(plant_utc_offset, how="left", on="plant_id_eia")
    # Some of the timezones in the plants_entity_eia table may be missing,
    # but none of the CEMS plants should be.
    if not df["utc_offset"].notna().all():
        missing_plants = df.loc[df["utc_offset"].isna(), "plant_id_eia"].unique()
        raise ValueError(
            "utc_offset should never be missing for CEMS plants, but was missing " +
            "for these: " + str(list(missing_plants))
            )
    # Add the offset from UTC. CEMS data don't have DST, so the offset is
    # always the same for a given plant.
    df["operating_datetime_utc"] = df["op_datetime_naive"] + df["utc_offset"]
    del df["op_date"], df["op_hour"], df["op_datetime_naive"], df["utc_offset"]
    return df


def _load_plant_utc_offset(pudl_engine):
    """Load the UTC offset each plant
    :param: pudl_engine A connection to the sqlalchemy database
    :return: A pandas DataFrame, with columns plant_id_eia and utc_offset

    CEMS times don't change for DST, so we get get the UTC offset by using the
    offset for the plants' timezones in January.
    """
    import pytz

    plants_eia_entity_select = sa.sql.select(
        [pudl.models.entities.PUDLBase.metadata.tables["plants_entity_eia"]]
    )
    # TODO: that this reads all the columns. It would be better to select a subset.
    timezones = pd.read_sql(plants_eia_entity_select, pudl_engine)[
        ["plant_id_eia", "timezone"]
    ].dropna()
    # Some plants lack the info to get a timezone. None of these plants are in CEMS.
    jan1 = pd.datetime(2011, 1, 1)  # year doesn't matter
    timezones["utc_offset"] = timezones["timezone"].apply(
        lambda tz: pytz.timezone(tz).localize(jan1).utcoffset()
    )
    del timezones["timezone"]
    return timezones


def harmonize_eia_epa_orispl(df):
    """
    Harmonize the ORISPL code to match the EIA data -- NOT YET IMPLEMENTED

    Args:
        df(pandas.DataFrame): A CEMS hourly dataframe for one year-month-state
    Output:
        pandas.DataFrame: The same data, with the ORISPL plant codes corrected
        to  match the EIA.

    The EIA plant IDs and CEMS ORISPL codes almost match, but not quite. See
    https://www.epa.gov/sites/production/files/2018-02/documents/egrid2016_technicalsupportdocument_0.pdf#page=104
    for an example.

    Note that this transformation needs to be run *before* fix_up_dates, because
    fix_up_dates uses the plant ID to look up timezones.
    """
    # TODO: implement this.
    return df


def add_facility_id_unit_id_epa(df):
    """Harmonize columns that are added later

    The load into Postgres checks for consistent column names, and these
    two columns aren't present before August 2008, so add them in.

    Args:
        df (pd.DataFrame): A CEMS dataframe
    Returns:
        The same DataFrame guaranteed to have int facility_id and unit_id_epa cols
    """
    if ("facility_id" not in df.columns) or ("unit_id_epa" not in df.columns):
        # Can't just assign np.NaN and get an integer NaN, so make a new array
        # with the right shape:
        na_col = pd.array(np.full(df.shape[0], np.NaN), dtype="Int64")
        if "facility_id" not in df.columns:
            df["facility_id"] = na_col
        if "unit_id_epa" not in df.columns:
            df["unit_id_epa"] = na_col
    return df


def _all_na_or_values(series, values):
    """Test whether every element in the series is either missing or in values

    This is fiddly because isin() changes behavior if the series is totally NaN
    (because of type issues)
    Demo: x = pd.DataFrame({'a': ['x', np.NaN], 'b': [np.NaN, np.NaN]})
    x.isin({'x', np.NaN})

    Args:
        series (pd.Series): A data column
        values (set): A set of values
    Returns:
        True or False
    """
    series_excl_na = series[series.notna()]
    if not len(series_excl_na):
        out = True
    elif series_excl_na.isin(values).all():
        out = True
    else:
        out = False
    return out


def correct_gross_load_mw(df):
    """Fix values of gross load that are wrong by orders of magnitude"""
    # Largest fossil plant is something like 3500 MW, and the largest unit
    # in the EIA 860 is less than 1500. Therefore, assume they've done it
    # wrong (by writing KWh) if they report more.
    # (There is a cogen unit, 54634 unit 1, that regularly reports around
    # 1700 MW. I'm assuming they're correct.)
    # This is rare, so don't bother most of the time.
    bad = df["gross_load_mw"] > 2000
    if bad.any():
        df.loc[bad, "gross_load_mw"] = df.loc[bad, "gross_load_mw"] / 1000
    return df


def transform(pudl_engine, epacems_raw_dfs, verbose=True):
    """Transform EPA CEMS hourly"""
    if verbose:
        print("Transforming tables from EPA CEMS:")
    # epacems_raw_dfs is a generator. Pull out one dataframe, run it through
    # a transformation pipeline, and yield it back as another generator.
    plant_utc_offset = _load_plant_utc_offset(pudl_engine)
    for raw_df_dict in epacems_raw_dfs:
        # There's currently only one dataframe in this dict at a time, but
        # that could be changed if you want.
        for yr_st, raw_df in raw_df_dict.items():
            df = (
                raw_df.fillna(pc.epacems_columns_fill_na_dict)
                .pipe(harmonize_eia_epa_orispl)
                .pipe(fix_up_dates, plant_utc_offset=plant_utc_offset)
                .pipe(add_facility_id_unit_id_epa)
                .pipe(correct_gross_load_mw)
            )
            yield {yr_st: df}
