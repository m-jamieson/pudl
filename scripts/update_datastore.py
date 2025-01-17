#!/usr/bin/env python
"""A script for fetching public utility data from reporting agency servers."""

import sys
import argparse
import pudl
from pudl.settings import SETTINGS
import pudl.constants as pc

# require modern python
if not sys.version_info >= (3, 6):
    raise AssertionError(
        f"PUDL requires Python 3.6 or later. {sys.version_info} found."
    )


def parse_command_line(argv):
    """
    Parse command line arguments. See the -h option.

    :param argv: arguments on the command line must include caller file name.
    """
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-q',
        '--quiet',
        dest='verbose',
        action='store_false',
        help="Quiet mode. Suppress download progress indicators and warnings.",
        default=True
    )
    parser.add_argument(
        '-z',
        '--zip',
        dest='unzip',
        action='store_false',
        help="Do not unzip downloaded data files.",
        default=True
    )
    parser.add_argument(
        '-c',
        '--clobber',
        action='store_true',
        help="Clobber existing zipfiles in the datastore if they exist.",
        default=False
    )
    parser.add_argument(
        '-d',
        '--datadir',
        type=str,
        help="""Path to the top level datastore directory. (default:
        %(default)s).""",
        default=SETTINGS['data_dir']
    )
    parser.add_argument(
        '-s',
        '--sources',
        nargs='+',
        choices=pc.data_sources,
        help="""List of data sources which should be downloaded.
        (default: %(default)s).""",
        default=pc.data_sources
    )
    parser.add_argument(
        '-y',
        '--years',
        dest='years',
        nargs='+',
        help="""List of years for which data should be downloaded. Different
        data sources have differet valid years. If data is not available for a
        specified year and data source, it will be ignored. If no years are
        specified, all available data will be downloaded for all requested data
        sources.""",
        default=[]
    )
    parser.add_argument(
        '-n',
        '--no-download',
        dest='no_download',
        action='store_true',
        help="Do not download data files, only unzip ones that are already present.",
        default=False
    )
    parser.add_argument(
        '-t',
        '--states',
        nargs='+',
        choices=pc.cems_states.keys(),
        help="""List of two letter US state abbreviations indicating which
        states data should be downloaded. Currently only applicable to the EPA's
        CEMS dataset.""",
        default=pc.cems_states.keys()
    )

    arguments = parser.parse_args(argv[1:])
    return arguments


def main():
    """Main function controlling flow of the script."""
    import concurrent.futures

    args = parse_command_line(sys.argv)

    # Generate a list of valid years of data to download for each data source.
    # If no years were specified, use the full set of valid years.
    # If years were specified, keep only th years which are valid for that
    # data source, and optionally output a message saying which years are
    # being ignored because they aren't valid.
    yrs_by_src = {}
    for src in args.sources:
        if not args.years:
            yrs_by_src[src] = pc.data_years[src]
        else:
            yrs_by_src[src] = [int(yr) for yr in args.years
                               if int(yr) in pc.data_years[src]]
            bad_yrs = [int(yr) for yr in args.years
                       if int(yr) not in pc.data_years[src]]
            if args.verbose and bad_yrs:
                print("Invalid {} years ignored: {}.".format(src, bad_yrs))

    with concurrent.futures.ThreadPoolExecutor() as executor:
        for src in args.sources:
            for yr in yrs_by_src[src]:
                executor.submit(pudl.datastore.update, src, yr, args.states,
                                clobber=args.clobber,
                                unzip=args.unzip,
                                verbose=args.verbose,
                                datadir=args.datadir,
                                no_download=args.no_download)


if __name__ == '__main__':
    sys.exit(main())
