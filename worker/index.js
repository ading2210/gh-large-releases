import mime from "mime";

function hex_to_b64(hex) {
  return btoa(hex.match(/\w{2}/g).map(function(a) {
    return String.fromCharCode(parseInt(a, 16));
  }).join(""));
}

async function concat_files(writable, urls) {
  let chunk_urls = [...urls];
  let chunk_url, options;
  while ([chunk_url, options] = chunk_urls.shift()) {
    let chunk_response = await fetch(chunk_url, options);
    await chunk_response.body.pipeTo(writable, {preventClose: chunk_urls.length > 0});
  }
}

function github_request_options(env, {accept} = {}) {
  return {
    headers: {
      "User-Agent": "cf-workers",
      "Accept": accept || "application/vnd.github+json",
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "X-GitHub-Api-Version": "2022-11-28"  
    }
  }
}

async function get_release(repo, tag, env) {
  let api_release_url = `https://api.github.com/repos/${repo}/releases/tags/${tag}`;
  let api_releases_url = `https://api.github.com/repos/${repo}/releases`;
  let release_response = await fetch(api_release_url, github_request_options(env));

  if (release_response.ok) {
    return await release_response.json();
  }

  else {
    let releases_response = await fetch(api_releases_url, github_request_options(env));
    if (!releases_response.ok) 
      return null;
    let releases = await releases_response.json();
    for (let release of releases) {
      if (release.tag_name === tag)
        return release;
    }
    return null;
  }
}

function find_next_page(link_header) {
  if (!link_header)
    return null;
  let link_regex = /<(.+?)>; rel="(.+?)"/gm;
  let matches = link_header.matchAll(link_regex);
  for (let [match, url, rel] of matches) {
    if (rel === "next") {
      return url;
    }
  }
}

async function get_assets(repo, tag, env) {
  let release = await get_release(repo, tag, env);
  if (!release)
    return {};
  let api_assets_url = `https://api.github.com/repos/${repo}/releases/${release.id}/assets?per_page=100`;
  let assets_response = await fetch(api_assets_url, github_request_options(env));

  let assets_list = [...await assets_response.json()]
  let next_page = find_next_page(assets_response.headers.get("link"));
  while (next_page) {
    let next_page_response = await fetch(next_page, github_request_options(env));
    assets_list.push(...next_page_response.json());
    next_page = find_next_page(next_page_response.headers.get("link"));
  }

  let assets = {};
  for (let asset of assets_list) {
    assets[asset.name] = asset;
  }
  return assets;
}

async function fetch_big_chunks(request, repo, tag, file, env) {
  let use_auth = false;
  let assets = null;

  let manifest_url = `https://github.com/${repo}/releases/download/${tag}/${file}.manifest`;
  let response = await fetch(manifest_url);
  
  if (!response.ok) {
    if (!env.GITHUB_TOKEN)
      return new Response("404 not found - no public asset manifest available", {status: 404});

    use_auth = true;
    assets = await get_assets(repo, tag, env);
    let manifest_asset = assets[`${file}.manifest`];
    if (!manifest_asset) 
      return new Response("404 not found - no manifest available", {status: 404});
    
    response = await fetch(manifest_asset.url, github_request_options(env, {
      accept: "application/octet-stream"
    }));
    if (!response.ok)
      return new Response("404 not found - failed to download manifest", {status: 404});
  }

  let manifest = await response.json();
  let headers = {
    "Content-Type": mime.getType(manifest.name) || "application/octet-stream",
    "Content-Disposition": `attachment; filename="${manifest.name}"`,
    "Content-Length": manifest.size,
    "Content-Digest": `sha-256=:${hex_to_b64(manifest.hash)}:`,
    "ETag": `"${manifest.hash}"`
  }

  if (request.method === "HEAD")
    return new Response(null, {headers});

  let chunk_paths;
  if (use_auth) {
    chunk_paths = manifest.chunks.map(chunk => {
      return [assets[chunk].url, github_request_options(env, {
        accept: "application/octet-stream"
      })];
    });
  }
  else {
    chunk_paths = manifest.chunks.map(chunk => {
      return [`https://github.com/${repo}/releases/download/${tag}/${chunk}`, {}];
    });  
  }

  let { readable, writable } = new FixedLengthStream(manifest.size);
  let fetch_impl = url => env.WORKER_B.fetch(url);
  concat_files(writable, chunk_paths, fetch_impl);

  return new Response(readable, {headers, status: 200});
}

export default {
  async fetch(request, env) {
    let url = new URL(request.url);
    let path = url.pathname.substring(1);
    if (request.method !== "GET" && request.method !== "HEAD")
      return new Response("405 method not allowed", {status: 405});
    if (url.pathname === "/") 
      return Response.redirect("https://github.com/ading2210/gh-large-releases");

    let path_parts = path.split("/");
    if (path_parts.length != 6) {
      return new Response("404 not found - bad url path", {status: 404});
    }

    //mimick the github download url, like this:
    //https://github.com/USER_NAME/REPO_NAME/releases/download/TAG_NAME/FILE_NAME
    let repo = path_parts.slice(0, 2).join("/");
    let tag = path_parts[4];
    let file = path_parts[5];
    
    return fetch_big_chunks(request, repo, tag, file, env);
  }
};