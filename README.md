pywb Wayback Web Recorder (Archiver)
======================================

**Note: this is an older prototype. We suggest taking a look at https://github.com/webrecorder/webrecorder, the Docker deployment for https://webrecorder.io/ which includes improved features and will be more maintained than this prototype**

This project provides a bare-bones example of how to create a simple web recording and replay system.

This project demonstrates how to create a simple web recorder tool by combining [pywb](https://github.com/ikreymer/pywb) (python wayback) web archive replay tools and [warcprox](https://github.com/internetarchive/warcprox) HTTP/S recording WARC proxy.

For additional reference, please consult the pywb and warcprox docs.

*For more reference, https://webrecorder.io is a hosted service built using some of the same tools.*


Basic Usage
-----------

To start, simply install with `pip install -r requirements.txt` under a Python 2.7.x environment.

Then, run `python pywb-webrecorder.py`

The `pywb-webrecorder.py` script will start an instance of pywb, warcprox and timed cdx index updater. 
pywb will be running on port 8080 and warcprox on port 9001 by default.

warcprox will store each WARC that is being written to (one at a time) into the **./recording/** directory. Once completed (or on shutdown), WARCs
will be moved to the **./done/** directory.

(All settings can be adjusted in [config.yaml](https://github.com/ikreymer/pywb-webrecorder/blob/master/config.yaml))


The pywb web app running on port 8080 will have the following endpoints available:


*  **/live/*url*** -- Fetch a live version of *url* (same as `live-rewrite-server` in pywb)

*  **/record/*url*** -- Fetch a live version of *url* but through warcprox recording proxy, recording all traffic.

*  **/replay/*url*** -- Replay an archived version of *url* if found from `./recording` or `./done` dirs. Display 404 if not archived. Standard pywb Wayback behavior.

*  **/replay-record/*url*** -- Replay an archived version of *url* if found from `./recording` or `./done` dirs. If not available, internally call the **/record/** handler to record a new copy of *url*.  

 
### Archive On-Demand

The **replay-record** endpoint demonstrates way to auto-record any missing resources from an existing archive.

The first time a resource is requested, it will be recorded. On each subsequent request (after the cdx has been updated), it will be replayed from an existing WARC.

The banner will contain either **live fetch** or **archived page** to indicate whether the page was live or archived.


How it Works
------------

pywb features a 'live rewrite' replay mode which fetches live web content and displays it same as if it was read from an archive file. (See the `live-rewrite-server` tool).

With pywb >= 0.5.0, it is now possible to specify a proxy server for the live fetching. This allows the live fetching to go through warcprox,
which proxies HTTP/S traffic and records it to WARC files.

The **/record/** endpoint is configured to fetch live content via the proxy on port 9001, while **/live/** access point just fetches live without recording.

In some cases, it is useful to record only when content is missing from an archive. pywb 0.5.0 includes a new fallback mechanism which allows
pywb to call a different handler instead of showing a 404.

The **/replay-record/** endpoint uses this feature to provide replay of archive content from WARCS in either `./recording` or `./done`. However, if a resource is not found, the request is delegated to **/record/** and a new recording is made.
(The **/replay/** endpoint just provides regular replay without auto recording)


### Index Updating

All the above functionality is provided by pywb and warcprox side-by-side.

The last missing piece is automatically updating the CDX index for pywb.

pywb does not provide a way to dynamically add CDX indexs on the fly. However, since the cdx is read on each request,
it is possible (and more efficient) to simply update an existing CDX index while pywb is running.

pywb starts with two cdx files `./recording/index.cdx` and `./done/index.cdx`, which may be updated as new content is recorded.

This `pywb-webrecorder.py` bootstrap script launches pywb and warcprox as subprocesses, then starts a periodic CDX updater, running
every few seconds (configured by `update_freq` property in config.yaml)

Of course, There are many ways to do this. For simplicity, the following approach is taken:

The periodic updater finds the latest WARC open by warcprox, a file ending in `.warc.gz.open`, and checks to see if it has been updated.
If it has, the updater calls the pywb `cdx-indexer` on the open file to create a new sorted `./recording/index.cdx`.

When warcprox is finished with a file, the `.open` extension is dropped. The updater also checks for any `.warc.gz` files and moves
them to the `./done` directory and regenerates `./done/index.cdx`. This happens on startup, shutdown or whenever the curr open file is no longer accessible.

On graceful shutdown (with SIGTERM), pywb-webrecorder.py also shuts down pywb and warcprox.

After graceful shutdown, the ./done/ dir should contain all the finished warcs and recording should be empty.

### Other Settings

The config.yaml file contains the command line settings for starting pywb and warcprox. Please refer to [warcprox README](https://github.com/internetarchive/warcprox/blob/master/README.rst) for command line options, such as changing the max WARC size or idle before rotating warcs, filenames, etc...

The max WARC size and max idle time options may be especially useful for adjusting how long a WARC file remains open and when it is moved
to `./done/` directory.

For instance, to set a WARC file to be considered done when no new content has been recorded for 60 seconds OR when size exceeds 1Kb, the
`recorder_exec` setting in the config can be modified as follows: `recorder_exec: 'warcprox --rollover-idle-time 60 -s 1000 ...`


uWSGI is used to run pywb but other WSGI containers can of course be used instead.

The config also demonstrates use of custom home page and error pages with pywb:
* [index.html](https://github.com/ikreymer/pywb-webrecorder/blob/master/html/index.html) is a simple custom home page for pywb-webrecorder
* [error.html](https://github.com/ikreymer/pywb-webrecorder/blob/master/html/error.html) modifies the standard pywb error page to also include an explicit **/record/** link for 'not found' errors (only makes sense when using **/replay/** endpoint).

#### A note on Dedup and Revisits

warcprox uses its own dedup db, written to `dedup.db` by default. The dedup scheme is decoupled from the actual WARC file being present/available. Thus, if removing warcs from `./done`, be sure to also delete `dedup.db` to avoid revisit records to WARCs that no longer
exist (unless that is the intent).
By default, dedup.db is persisted when pywb-webrecorder is shutdown.
When starting pywb-webrecorder, the dedup.db can be automatically deleted and created anew via the `-f` flag: `python pywb-webrecorder.py -f` 


## Contributions

This project is intended as a demo of different web recording scenarios that could be used by combining pywb and warcprox. The project is under the MIT license and can be used freely (although pywb and warcprox may have different licenses).

Changes and adaptions to different use cases is encouraged. Feedback and pull requests encouraged!
