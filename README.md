# Large Releases in Github Actions

This Github Action allows you to upload files which are larger than 2GB to [Github Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases). It bypasses the 2GB file size limit set by Github by splitting the files into 2GB parts, and using Cloudflare Workers to concatenate them together when downloaded.

## Actions Usage
Simply add this as a step to your Github Actions workflow, like this:

```yaml
name: build
on: [push]

jobs:
  build:
    permissions:
      contents: write

    runs-on: ubuntu-latest
    steps:
      - name: download repo
        uses: actions/checkout@v4
      
      - name: run build
        run: |
          sudo ./build.sh

      - name: create release
        uses: ading2210/gh-large-releases@v1
        if: startsWith(github.ref, 'refs/tags/')
        with:
          draft: true
          files: out/*.zip
```

The action accepts the following arguments:

```yaml
inputs:
  repository:
    description: "Repository to make releases against, in <owner>/<repo> format."
    required: false
    default: ${{ github.repository }}
  files:
    description: "A list of files to upload to the release. Glob syntax may be used here."
    required: true
  token:
    description: "The GitHub access token to use."
    required: false
    default: ${{ github.token }}
  workspace:
    description: "The path to the default working directory."
    required: false
    default: ${{ github.workspace }}
  worker_url:
    description: "Override the URL to the Cloudflare Worker that serves the release files."
    required: false
  
  tag_name:
    description: "The name of the tag."
    required: false
    default: ${{ github.ref }}
  target_commitish:
    description: "Specifies the commitish value that determines where the Git tag is created from."
    required: false
  name:
    description: "The name of the release."
    required: false
  body:
    description: "Text describing the contents of the release."
    required: false
  draft:
    description: "`true` to create a draft (unpublished) release, `false` to create a published one."
    required: false
  prerelease:
    description: "`true` to identify the release as a prerelease. `false` to identify the release as a full release."
    required: false
  make_latest:
    description: "Specifies whether this release should be set as the latest release for the repository."
    required: false
  generate_release_notes:
    description: "Whether to automatically generate the name and body for this release."
    required: false
  discussion_category_name:
    description: "If specified, a discussion of the specified category is created and linked to the release."
    required: false
```

When releases are uploaded by the action, the release description will include a table of all the files and the download URL provided by the CF worker. The URL looks like this:
```
https://gh-large-releases.ading2210.workers.dev/USER_NAME/REPO_NAME/releases/download/TAG_NAME/FILE_NAME
```

## CF Workers Usage

The Cloudflare worker supports downloading private releases, as long as you provide a Github API token as a secret. 

To deploy your own worker with your own token, clone this repo and run the following commands:
```
npm i
npm run deploy
npm run deploy_set_token
```

When prompted, paste your Github token into Wrangler.

Then, you can set the `worker_url` option when invoking the Github action. 

## License

This repository is licensed under the GNU LGPL v3.

> This license is mainly applied to libraries. You may copy, distribute and modify the software provided that modifications are described and licensed for free under LGPL. Derivatives works (including modifications or anything statically linked to the library) can only be redistributed under LGPL, but applications that use the library don't have to be.
> 
> \- From [tldrlegal.com](https://www.tldrlegal.com/license/gnu-lesser-general-public-license-v3-lgpl-3)