import argparse
import pathlib
import hashlib
import json
import math
import threading
import queue
import re
import logging

import httpx
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

session = httpx.Client(follow_redirects=True)

logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_size(total_size, chunk_size, chunk_count, i):
  if i == chunk_count - 1:
    return total_size % chunk_size
  return chunk_size

def human_readable_size(size, decimal_places=2):
  for unit in ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]:
    if size < 1024.0 or unit == "PiB":
      break
    size /= 1024.0
  return f"{size:.{decimal_places}f} {unit}"

def upload_asset(args, name, data, length):
  release = get_release(args)
  url = f"https://uploads.github.com/repos/{args.repository}/releases/{release['id']}/assets?name={name}"
  r = session.post(url, data=data, headers={
    "Content-Type": "application/octet-stream",
    "Content-Length": str(length)
  })
  r.raise_for_status()

def process_file(args, path):
  chunk_names = []
  original_size = path.stat().st_size
  #big_chunk_size = min(original_size, 2*1024*1024*1024)
  big_chunk_size = min(original_size, 40*1024*1024)
  small_chunk_size = 25*1024*1024 

  total_size = path.stat().st_size
  big_chunks = math.ceil(total_size / big_chunk_size)
  sha256sum = hashlib.sha256()

  with open(path, "rb") as read_file:
    for i in range(0, big_chunks):
      new_name = f"{path.name}.{i:04}"
      big_size = get_size(total_size, big_chunk_size, big_chunks, i)
      small_chunks = math.ceil(big_size / small_chunk_size)

      def chunk_generator():
        for j in range(0, small_chunks):
          small_size = get_size(big_size, small_chunk_size, small_chunks, j)
          data = read_file.read(small_size)
          sha256sum.update(data)
          print(len(data))
          yield data
      
      chunk_names.append(new_name)
      upload_asset(args, new_name, chunk_generator(), big_size)

  manifest = {
    "name": path.name,
    "hash": sha256sum.hexdigest(),
    "size": original_size,
    "chunk_size": big_chunk_size,
    "chunks": chunk_names
  }
  manifest_json = json.dumps(manifest, indent=2).encode()
  manifest_name = f"{path.name}.manifest"

  upload_asset(args, manifest_name, manifest_json, len(manifest_json))
  update_release_body(args)

#get the release we will use, creating one if needed
def get_release(args):
  url = f"https://api.github.com/repos/{args.repository}/releases/tags/{args.tag_name}"
  r = session.get(url)

  if r.status_code == 200:
    return r.json()
  else:
    return create_release(args)

#create a new release
def create_release(args):
  url = f"https://api.github.com/repos/{args.repository}/releases"
  payload = {
    "tag_name": args.tag_name,
    "target_commitish": args.target_commitish or None,
    "name": args.name or None, 
    "body": args.body or None,
    "draft": json.loads(args.draft) if args.draft else None,
    "prerelease": json.loads(args.prerelease) if args.prerelease else None,
    "discussion_category_name": args.discussion_category_name or None,
    "generate_release_notes": json.loads(args.generate_release_notes) if args.generate_release_notes else None, 
    "make_latest": args.make_latest or None
  }
  payload = {k: v for k, v in payload.items() if v is not None}
  r = session.post(url, json=payload)
  r.raise_for_status()
  return r.json()

#update release body to include links to the cf worker
def update_release_body(args):
  tag_start = "<!-- START_BIG_ASSET_LIST_DO_NOT_REMOVE -->"
  tag_end = "<!-- END_BIG_ASSET_LIST_DO_NOT_REMOVE -->"
  table_lines = [
    tag_start,
    "| File Name | Size | SHA-256 Hash |", 
    "| --------- | ---- | ------------ |"
  ]
  release = get_release(args)
  
  for asset in release["assets"]:
    if not asset["name"].endswith(".manifest"):
      continue
    r = session.get(asset["url"], headers={
      "Accept": "application/octet-stream"
    })
    print(r.content)
    manifest = r.json()
    print(manifest)
    table_lines.append(f"| {manifest['name']} | {human_readable_size(manifest['size'])} | `{manifest['hash']}` |")
  table_lines.append(tag_end)
  table_str = "\n".join(table_lines)
  
  table_regex = f"{tag_start}.+{tag_end}"
  body = release["body"] or ""
  if re.findall(table_regex, body):
    body = re.sub(table_regex, table_str, body, flags=re.S)
  else:
    body += f"\n\n{table_str}"
  
  url = f"https://api.github.com/repos/{args.repository}/releases/{release['id']}"
  r = session.patch(url, json={
    "body": body
  })
  r.raise_for_status()

if __name__ == "__main__":
  parser = argparse.ArgumentParser() 
  parser.add_argument("--repository")
  parser.add_argument("--files")
  parser.add_argument("--token")
  parser.add_argument("--workspace")
  parser.add_argument("--tag_name")
  parser.add_argument("--target_commitish")
  parser.add_argument("--name")
  parser.add_argument("--body")
  parser.add_argument("--draft")
  parser.add_argument("--prerelease")
  parser.add_argument("--make_latest")
  parser.add_argument("--generate_release_notes")
  parser.add_argument("--discussion_category_name")
  args = parser.parse_args()

  session.headers.update({
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {args.token}",
    "X-GitHub-Api-Version": "2022-11-28"
  })
  release = get_release(args)

  base_path = pathlib.Path(args.workspace).resolve()
  for file_name in args.files.split("\n"):
    file_path = base_path / file_name
    process_file(args, file_path)