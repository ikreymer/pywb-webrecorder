import yaml
import subprocess
import sys
import os
from datetime import datetime
import time
import atexit
import itertools
import signal

from pywb.warc import cdxindexer
from argparse import ArgumentParser


#=================================================================
class SubProcess(object):
    """
    Track a subprocess from command-line.
    Add atexit callback to terminate it on shutdown.
    """
    def __init__(self, cl):
        """
        Launch subprocess
        """
        args = cl.split(' ')
        self.name = args[0]
        self.proc = subprocess.Popen(args, stdout=sys.stdout)
        atexit.register(self.cleanup)

    def cleanup(self):
        """
        Terminate subprocess, wait for it to finish
        """
        try:
            print 'Shutting down ', self.name
            if self.proc:
                self.proc.terminate()

            self.proc.wait()
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


#=================================================================
class CDXUpdater(object):
    """
    Updates record and done cdx indexs
    """
    def __init__(self, record_dir, record_cdx,
                       done_dir, done_cdx):
        """
        Creates record and done dirs and empty cdxs on startup, if missing
        Register finish for shutdown callback
        """
        self.record_dir = record_dir
        self.record_cdx = record_cdx
        self.done_dir = done_dir
        self.done_cdx = done_cdx

        self.curr_open_warc = None
        self.last_mod = 0

        atexit.register(self.finish)

        # record dir
        if not os.path.isdir(record_dir):
            os.makedirs(record_dir)

        # clear record cdx
        with open(record_cdx, 'w') as fh:
            pass

        # done dir
        if not os.path.isdir(done_dir):
            os.makedirs(done_dir)

        # done cdx
        if not os.path.isfile(done_cdx):
            with open(done_cdx, 'w') as fh:
                pass

    def find_open_warc_and_move_done(self):
        """
        Scan record_dir and move any one warcs (ending in .warc.gz)
        to done_dir.

        (Move all but last '.warc.gz.open' to done as well)

        Store the last '.warc.gz.open' as curr_open_warc and return
        """

        any_done = False
        curr_open_warc = None

        for name in os.listdir(self.record_dir):
            if name.endswith('.warc.gz'):
                src = os.path.join(self.record_dir, name)
                dest = os.path.join(self.done_dir, name)
                os.rename(src, dest)
                any_done = True

            elif name.endswith('.warc.gz.open'):
                # only one warc can be 'open', move any others to done
                if curr_open_warc:
                    name_noopen = os.path.splitext(name)[0]
                    os.rename(curr_open_warc,
                              os.path.join(self.done_dir, name_noopen))

                curr_open_warc = os.path.join(self.record_dir, name)

        self.curr_open_warc = curr_open_warc
        self.modtime = 0

        # Rebuild done cdx
        if any_done:
            self.index_cdx(self.done_cdx, self.done_dir)

        return curr_open_warc

    def update(self):
        """
        Update record cdx if curr_open_warc has been modified

        If no curr_open_warc, or curr_open_warc is no longer
        available find a new one, move finished warcs to done
        """
        # if no curr_open_warc, find one
        if not self.curr_open_warc:
            if not self.find_open_warc_and_move_done():
                self.clear_cdx(self.record_cdx)
                return

        try:
            modtime = os.path.getmtime(self.curr_open_warc)
        except OSError:
            # if error checking curr_open_warc, see if its been
            # closed and a new one is now open
            if not self.find_open_warc_and_move_done():
                self.clear_cdx(self.record_cdx)
                return

            try:
                modtime = os.path.getmtime(self.curr_open_warc)
            except:
                self.clear_cdx(self.record_cdx)
                return

        # if modified time same as last time, nothing to update
        if modtime > 0 and modtime == self.modtime:
            return

        if self.index_cdx(self.record_cdx, self.curr_open_warc):
            self.modtime = modtime

    def finish(self):
        """
        Called on shutdown, finish cdx updater by
        moving all finished warcs to done, deleting
        record cdx if no more open warcs
        """
        # hopefully all warcs finished move them to done
        if not self.find_open_warc_and_move_done():
            # if no open warcs left, remove the record cdx
            # (since warc now moved to done)
            os.remove(self.record_cdx)

    def clear_cdx(self, output_cdx):
        """
        Empty the cdx file to clear old records
        (Can't delete as it is being looked up)
        """
        with open(output_cdx, 'w') as fh:
            pass

    def index_cdx(self, output_cdx, input_):
        """
        Output sorted, post-query resolving cdx from 'input_' warc(s)
        to 'output_cdx'. Write cdx to temp and rename to output_cdx
        when completed to ensure atomic updates of the cdx.
        """
        # Run cdx indexer
        temp_cdx = output_cdx + '.tmp.' + timestamp20()
        indexer_args = ['-s', '-p', temp_cdx, input_]

        try:
            cdxindexer.main(indexer_args)
        except Exception as exc:
            import traceback
            err_details = traceback.format_exc(exc)
            print err_details

            os.remove(temp_cdx)
            return False
        else:
            os.rename(temp_cdx, output_cdx)
            return True


#=================================================================
def timestamp20():
    """
    Create 20-digit timestamp, useful to timestamping temp files
    """
    now = datetime.utcnow()
    return now.strftime('%Y%m%d%H%M%S%f')


#=================================================================
def main():
    parser = ArgumentParser(description='pywb web recorder controller')

    parser.add_argument('-c', '--config', default='config.yaml',
                        action='store',
                        help='Config file to load pywb and recorder settings')

    parser.add_argument('-f', '--flushdedup',
                        action='store_true',
                        help='If set, removes current dedup.db file to start fresh')

    result = parser.parse_args()

    with open(result.config) as fh:
        config = yaml.load(fh)

    # set to recorded block
    config = config['recorder']

    # init updater
    updater = CDXUpdater(config['record_dir'], config['record_cdx'],
                         config['done_dir'], config['done_cdx'])

    # if flushdedup set, remove old dedup file
    if result.flushdedup:
        dedup_db = config.get('dedup_db')
        print 'Removing old dedup_db: ', dedup_db
        if dedup_db:
            try:
                os.remove(dedup_db)
            except (IOError, OSError):
                pass

    # start recorder subproc
    recorderp = SubProcess(config['recorder_exec'])

    # start pywb subproc
    pywbp = SubProcess(config['pywb_exec'])

    def cleanup_subp(signum, frame):
        pywbp.cleanup()
        recorderp.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup_subp)

    update_freq = int(config.get('update_freq', 1))

    while True:
        updater.update()
        time.sleep(update_freq)


#=================================================================
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
