import pathlib
import json

import util

def process_file(original, out_dir):
  original_hash = util.file_split(original, out_dir, 2*1024*1024*1024)
  original_size = original.stat().st_size
  chunks = sorted(out_dir.parent.rglob(f"{original.name}.*"))
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
  manifest_path = out_dir / f"{original.name}.manifest"
  manifest_path.write_text(manifest_json)

if __name__ == "__main__":
  base_dir = pathlib.Path(__file__).resolve().parent
  original_dir = base_dir / "data"
  out_dir = base_dir / "out"

  for original_zip in original_dir.rglob("*.zip"):
    process_file(original_zip, out_dir)