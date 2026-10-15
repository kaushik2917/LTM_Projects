"""Fetch public research files with explicit size limits; never download a folder tree."""
import argparse
import json
import re
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from app.datasets import DATA, sha256


class DownloadForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.fields = {}
        self.active = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("id") == "download-form":
            self.action = attrs.get("action")
            self.active = True
        if tag == "input" and self.active and attrs.get("name"):
            self.fields[attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.active = False


def download(url, path, max_bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    count = 0
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    response = opener.open(url, timeout=40)
    if "text/html" in response.headers.get("Content-Type", ""):
        form = DownloadForm()
        with response:
            form.feed(response.read(2 * 1024 * 1024).decode())
        if not form.action or urllib.parse.urlparse(form.action).hostname not in {"drive.usercontent.google.com", "drive.google.com"}:
            raise ValueError("Download unavailable: no recognized public Google Drive confirmation form")
        response = opener.open(form.action + "?" + urllib.parse.urlencode(form.fields), timeout=40)
    with response, temporary.open("wb") as output:
        if "text/html" in response.headers.get("Content-Type", ""):
            raise ValueError("Drive returned an access/quota page after confirmation")
        if int(response.headers.get("Content-Length", "0")) > max_bytes:
            raise ValueError("File exceeds configured download limit")
        while chunk := response.read(1024 * 1024):
            count += len(chunk)
            if count > max_bytes:
                raise ValueError("Download exceeds configured size limit; partial file retained")
            output.write(chunk)
    temporary.replace(path)
    metadata = {"source_url": url, "bytes": count, "sha256": sha256(path)}
    path.with_suffix(path.suffix + ".source.json").write_text(json.dumps(metadata, indent=2))
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["mitre", "optc-list", "optc-file", "optc-ground-truth"])
    parser.add_argument("--id")
    parser.add_argument("--name", default="optc-sample.json.gz")
    parser.add_argument("--max-mb", type=int, default=250)
    args = parser.parse_args()
    if args.kind == "optc-list":
        if not args.id or not re.fullmatch(r"[A-Za-z0-9_-]+", args.id):
            parser.error("A valid public folder ID is required")
        page = urllib.request.urlopen(f"https://drive.google.com/drive/folders/{args.id}", timeout=30).read().decode()
        print(json.dumps(sorted(set(re.findall(r'data-id="([^"]+)"[^>]+data-tooltip="([^"]+)"', page))), indent=2))
        return
    if args.kind == "mitre":
        url = "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack-19.2.json"
        target = DATA / "mitre" / "enterprise-attack-19.2.json"
    elif args.kind == "optc-ground-truth":
        url = "https://raw.githubusercontent.com/FiveDirections/OpTC-data/master/OpTCRedTeamGroundTruth.pdf"
        target = DATA / "optc" / "OpTCRedTeamGroundTruth.pdf"
    else:
        if not args.id or not re.fullmatch(r"[A-Za-z0-9_-]+", args.id):
            parser.error("A valid public file ID is required")
        if Path(args.name).name != args.name:
            parser.error("--name must be a filename without directories")
        url = f"https://drive.google.com/uc?export=download&id={args.id}"
        target = DATA / "optc" / args.name
    print(json.dumps(download(url, target, args.max_mb * 1024 * 1024), indent=2))


if __name__ == "__main__":
    main()
