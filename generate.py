import pathlib
import json

import util

def create_manifest(path, original, original_hash):
  original_size = original.stat().st_size
  chunks = sorted(path.parent.rglob(path.stem + ".*"))
  chunk_size = chunks[0].stat().st_size
  chunk_names = [c.name for c in chunks if c.suffix != ".manifest"]
  
  manifest = {
    "name": original.name,
    "hash": original_hash,
    "size": original_size,
    "chunk_size": chunk_size,
    "chunks": chunk_names
  }
  manifest_json = json.dumps(manifest, indent=2)
  path.write_text(manifest_json)

def process_file(path):
  original_hash = util.file_split(original_zip, 2*1024*1024*1024)
  manifest_path = path.with_name(path.name + ".manifest")
  create_manifest(manifest_path, original_zip, original_hash)

if __name__ == "__main__":
  base_dir = pathlib.Path(__file__).resolve().parent
  original_dir = base_dir / "data"

  for original_zip in original_dir.rglob("*.zip"):
    process_file(original_zip)