import argparse
import pathlib
import hashlib
import json
import math
import re
import logging
import traceback

import httpx

session = httpx.Client(follow_redirects=True)

logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_tag_name(tag_name):
  return tag_name.replace("refs/tags/", "", 1)

def get_size(total_size, chunk_size, chunk_count, i):
  if i == chunk_count - 1 and total_size % chunk_size > 0:
    return total_size % chunk_size
  return chunk_size

def pretty_size(size, decimal_places=2):
  for unit in ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]:
    if size < 1024.0 or unit == "PiB":
      break
    size /= 1024.0
  return f"{size:.{decimal_places}f} {unit}"

def upload_asset(args, release, assets, name, data, length):
  for asset in assets:
    if asset["name"] != name:
      continue
    logging.warning(f"asset {name} has already been uploaded, deleting now")
    delete_asset_url = f"https://api.github.com/repos/{args.repository}/releases/assets/{asset['id']}"
    delete_response = session.delete(delete_asset_url)
    delete_response.raise_for_status()

  url = f"https://uploads.github.com/repos/{args.repository}/releases/{release['id']}/assets?name={name}"
  r = session.post(url, data=data, timeout=httpx.Timeout(None), headers={
    "Content-Type": "application/octet-stream",
    "Content-Length": str(length)
  })
  r.raise_for_status()

def process_file(args, release, assets, path):
  chunk_names = []
  original_size = path.stat().st_size
  big_chunk_size = int(args.big_chunk_size) if args.big_chunk_size else 2000*1024*1024
  big_chunk_size = min(original_size, big_chunk_size)
  small_chunk_size = 25*1024*1024 

  total_size = path.stat().st_size
  big_chunks = math.ceil(total_size / big_chunk_size)
  sha_hash = hashlib.sha256()

  total_uploaded = 0
  with open(path, "rb") as read_file:
    for i in range(0, big_chunks):
      new_name = f"{path.name}.{i:04}"
      big_size = get_size(total_size, big_chunk_size, big_chunks, i)
      small_chunks = math.ceil(big_size / small_chunk_size)

      def chunk_generator():
        nonlocal total_uploaded
        for j in range(0, small_chunks):
          small_size = get_size(big_size, small_chunk_size, small_chunks, j)
          data = read_file.read(small_size)
          sha_hash.update(data)
          yield data
          total_uploaded += len(data)
          logger.info(f"uploaded {pretty_size(total_uploaded)} / {pretty_size(total_size)} of {path.name}")
      
      chunk_names.append(new_name)
      upload_asset(args, release, assets, new_name, chunk_generator(), big_size)

  manifest = {
    "name": path.name,
    "hash": sha_hash.hexdigest(),
    "size": original_size,
    "chunk_size": big_chunk_size,
    "chunks": chunk_names
  }
  manifest_json = json.dumps(manifest, indent=2).encode()
  manifest_name = f"{path.name}.manifest"

  upload_asset(args, release, assets, manifest_name, manifest_json, len(manifest_json))

#get the release we will use, creating one if needed
def get_release(args, retry=False):
  url = f"https://api.github.com/repos/{args.repository}/releases"
  r = session.get(url)
  r.raise_for_status()
  releases = r.json()

  for release in releases:
    if get_tag_name(release["tag_name"]) == get_tag_name(args.tag_name):
      return release
  return create_release(args)

#create a new release
def create_release(args):
  url = f"https://api.github.com/repos/{args.repository}/releases"
  payload = {
    "tag_name": get_tag_name(args.tag_name),
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

def find_next_page(link_header):
  if not link_header:
    return None
  link_regex = r'<(.+?)>; rel="(.+?)"'
  for url, rel in re.findall(link_regex, link_header):
    if rel == "next":
      return url

def get_assets(release, args):
  assets_url = f"https://api.github.com/repos/{args.repository}/releases/{release['id']}/assets?per_page=100"
  response = session.get(assets_url)
  response.raise_for_status()
  assets_list = response.json()

  next_page = find_next_page(response.headers.get("link"))
  while next_page:
    next_response = session.get(next_page)
    next_response.raise_for_status()
    assets_list += next_response.json()
    next_page = find_next_page(next_response.headers.get("link"))
  
  return assets_list

#update release body to include links to the cf worker
def update_release_body(args):
  tag_start = "<!-- START_BIG_ASSET_LIST_DO_NOT_REMOVE -->"
  tag_end = "<!-- END_BIG_ASSET_LIST_DO_NOT_REMOVE -->"
  table_lines = [
    tag_start,
    "Release files generated with [ading2210/gh-large-releases](https://github.com/ading2210/gh-large-releases).",
    "| File Name | Size | SHA-256 Hash |", 
    "| --------- | ---- | ------------ |"
  ]
  release = get_release(args)
  assets = get_assets(release, args)
  
  manifests = []
  for asset in assets:
    if not asset["name"].endswith(".manifest"):
      continue
    r = session.get(asset["url"], headers={
      "Accept": "application/octet-stream"
    })
    manifests.append(r.json())

  manifests.sort(key=lambda x: x["name"])
  for manifest in manifests:
    worker_url = args.worker_url or "https://gh-releases.ading2210.workers.dev"
    download_url = f"{worker_url}/{args.repository}/releases/download/{get_tag_name(args.tag_name)}/{manifest['name']}"
    download_link = f"[{manifest['name']}]({download_url})"
    line = f"| {download_link} | {pretty_size(manifest['size'])} | <sub><sup>`{manifest['hash']}`</sub></sup> |"
    table_lines.append(line)
    
  table_lines.append("> [!IMPORTANT]")
  table_lines.append("> Download files from the links in the table above, instead of the assets list.")

  table_lines.append(tag_end)
  table_str = "\n".join(table_lines)
  table_regex = f"{tag_start}.+{tag_end}"
  body = release["body"] or ""

  if re.findall(table_regex, body, flags=re.S):
    body = re.sub(table_regex, table_str, body, flags=re.S)
  else:
    body += f"\n\n{table_str}"
  
  url = f"https://api.github.com/repos/{args.repository}/releases/{release['id']}"
  payload = {
    "tag_name": get_tag_name(args.tag_name),
    "target_commitish": args.target_commitish or None,
    "name": args.name or None, 
    "body": body,
    "draft": json.loads(args.draft) if args.draft else None,
    "prerelease": json.loads(args.prerelease) if args.prerelease else None,
    "discussion_category_name": args.discussion_category_name or None,
    "make_latest": args.make_latest or None
  }
  payload = {k: v for k, v in payload.items() if v is not None}
  r = session.patch(url, json=payload)
  r.raise_for_status()

if __name__ == "__main__":
  parser = argparse.ArgumentParser() 
  parser.add_argument("--repository")
  parser.add_argument("--files")
  parser.add_argument("--token")
  parser.add_argument("--workspace")
  parser.add_argument("--worker_url")
  parser.add_argument("--tag_name")
  parser.add_argument("--target_commitish")
  parser.add_argument("--name")
  parser.add_argument("--body")
  parser.add_argument("--draft")
  parser.add_argument("--prerelease")
  parser.add_argument("--make_latest")
  parser.add_argument("--generate_release_notes")
  parser.add_argument("--discussion_category_name")
  parser.add_argument("--big_chunk_size")
  args = parser.parse_args()

  session.headers.update({
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {args.token}",
    "X-GitHub-Api-Version": "2022-11-28"
  })
  release = get_release(args)
  assets = get_assets(release, args)

  base_path = pathlib.Path(args.workspace).resolve()
  for file_glob in args.files.split("\n"):
    for file_path in base_path.glob(file_glob.strip()):
      try:
        process_file(args, release, assets,file_path)
      except Exception as e:
        logger.error("caught error:")
        logger.error(traceback.format_exc())
        logger.error("retrying file upload")
        process_file(args, release, assets,file_path)

  update_release_body(args)