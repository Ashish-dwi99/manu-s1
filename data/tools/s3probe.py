"""Anonymous listing and small reads from the public Indian High Court judgments bucket (CC-BY-4.0, Dattam Labs)."""
import re
import sys
import urllib.parse
import urllib.request

BUCKET = "https://indian-high-court-judgments.s3.amazonaws.com"


def ls(prefix: str, delimiter: str = "/", max_keys: int = 1000) -> tuple[list[str], list[tuple[str, int]]]:
    q = urllib.parse.urlencode({"list-type": "2", "prefix": prefix, "delimiter": delimiter, "max-keys": max_keys})
    body = urllib.request.urlopen(f"{BUCKET}/?{q}", timeout=60).read().decode()
    dirs = re.findall(r"<CommonPrefixes><Prefix>(.*?)</Prefix></CommonPrefixes>", body)
    files = [(k, int(s)) for k, s in re.findall(r"<Key>(.*?)</Key>.*?<Size>(\d+)</Size>", body)]
    return dirs, files


def get(key: str, dest: str) -> None:
    urllib.request.urlretrieve(f"{BUCKET}/{urllib.parse.quote(key)}", dest)


if __name__ == "__main__":
    dirs, files = ls(sys.argv[1] if len(sys.argv) > 1 else "")
    for d in dirs[:60]:
        print("DIR ", d)
    for k, s in files[:60]:
        print("FILE", s, k)
