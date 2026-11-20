"""The command line: nwkills <capture.pcapng> [options]."""
import argparse
import os
import sys

from .pipeline import Cancelled, KillReportPipeline, PipelineOptions


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Read Mount & Blade: Warband Napoleonic Wars kills from a Wireshark capture (client side).')
    parser.add_argument('pcap', nargs='?', help='.pcapng captured while you were connected to the server')
    parser.add_argument('--out', help='output CSV (default: <pcap>_kills.csv)')
    parser.add_argument('--port', type=int, help='server UDP port (default: auto-detect)')
    parser.add_argument('--me', help='part of your own player name (used as the local player)')
    parser.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2)))
    parser.add_argument('--cache', help='pickle file to save/reuse decoded packets (re-run the kill logic without re-decoding)')
    parser.add_argument('--limit', type=int, help='only decode the first N packets (test)')
    return parser


def options_from_arguments(arguments) -> PipelineOptions:
    """`arguments` needs: pcap, out, port, me, jobs, cache, limit (an argparse namespace, or the window's equivalent)."""
    return PipelineOptions(capture_path=arguments.pcap, kills_path=arguments.out, server_port=arguments.port, own_name_part=arguments.me,
                           process_count=arguments.jobs, cache_path=arguments.cache, packet_limit=arguments.limit)


def run(arguments, log=print, progress=lambda stage, fraction: None):
    """The whole pipeline. Returns the paths of the CSV files written. progress(stage, fraction 0..1 inside that stage) may raise Cancelled to stop."""
    return KillReportPipeline().run(options_from_arguments(arguments), log, progress)


def main(argv=None):
    parser = build_argument_parser()
    arguments = parser.parse_args(argv)
    if not arguments.pcap:
        parser.error('give the .pcapng capture to read (or drag it onto nwkills.exe)')
    try:
        run(arguments)
    except RuntimeError as error:
        sys.exit(str(error))


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
