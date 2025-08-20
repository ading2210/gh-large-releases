import pathlib
import hashlib
import math

def get_size(total_size, chunk_size, chunk_count, i):
  if i == chunk_count - 1:
    return total_size % chunk_size
  return chunk_size

def file_split(path, out_dir, big_chunk_size, small_chunk_size=(25*1024*1024)):
  total_size = path.stat().st_size
  big_chunks = math.ceil(total_size / big_chunk_size)
  sha256sum = hashlib.sha256()

  with open(path, "rb") as read_file:
    for i in range(0, big_chunks):
      new_path = out_dir / f"{path.name}.{i:04}"
      big_size = get_size(total_size, big_chunk_size, big_chunks, i)
      small_chunks = math.ceil(big_size / small_chunk_size)

      with open(new_path, "wb") as write_file:
        for j in range(0, small_chunks):
          small_size = get_size(big_size, small_chunk_size, small_chunks, j)
          data = read_file.read(small_size)
          write_file.write(data)
          sha256sum.update(data)
  
  return sha256sum.hexdigest()