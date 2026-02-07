from pathlib import Path
import os

defaultdir = str(Path.home()) + "/"

p = {"pathkeys": ["path_data"], "path_data": defaultdir + ".rreader/"}


FEEDS_FILE_NAME = os.path.join(p["path_data"], "feeds.json")


for d in p["pathkeys"]:
    if not os.path.exists(p[d]):
        os.mkdir(p[d])
