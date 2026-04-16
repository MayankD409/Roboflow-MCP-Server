# Releasing

Short playbook for cutting a release. Maintainer only.

## Prep

1. Make sure `develop` is green: `make check`.
2. Branch off `develop`:
   ```bash
   git checkout develop && git pull
   git checkout -b release/x.y.z
   ```
3. Bump the version in `pyproject.toml` -> `[project] version = "x.y.z"`.
   `__version__` is read from installed package metadata, so no other file
   needs to change.
4. Finalize `CHANGELOG.md`:
   - Move everything under `## [Unreleased]` into a new
     `## [x.y.z] - YYYY-MM-DD` section.
   - Leave an empty `## [Unreleased]` at the top for the next cycle.
   - Update the comparison links at the bottom.
5. Run `make check`. Green.
6. Commit, push, and open a PR:
   - **Base**: `main`
   - **Head**: `release/x.y.z`
   - **Label**: `release`

## Ship

Once the PR merges into `main`:

```bash
git checkout main && git pull
git tag -a vx.y.z -m "vx.y.z"
git push origin vx.y.z
```

The tag push triggers `.github/workflows/release.yml`, which:

1. Runs the test suite one more time.
2. Builds the sdist and wheel with `uv build`.
3. Publishes both artifacts to PyPI via a Trusted Publisher (OIDC); no API
   token is stored in the repo.
4. Creates a GitHub Release with auto-generated notes and attaches the
   same artifacts.

## Close out

Back-merge `main` into `develop` so the merge commit and tag show up on
`develop` too:

```bash
git checkout develop && git pull
git merge --no-ff main -m "chore: back-merge vx.y.z into develop"
git push
```

### Handling AA (add/add) conflicts on back-merge

When the release branch bumped the same files `develop` also has
(`pyproject.toml`, `CHANGELOG.md`, `uv.lock`), git will report them as
`AA` conflicts on the back-merge. Take `main`'s side -- the release is
the source of truth for those files:

```bash
git checkout --theirs \
  pyproject.toml \
  CHANGELOG.md \
  uv.lock
git add pyproject.toml CHANGELOG.md uv.lock
git commit --no-edit
git push
```

Hotfix branches have the same shape, so the same recipe applies there.

## Delete the release branch

Once `main` and `develop` both contain the release merge, delete the branch:

```bash
git branch -d release/x.y.z
git push origin --delete release/x.y.z
```

(If branch protection auto-delete is on, the remote branch goes away on
merge and only the local delete is needed.)

## PyPI trusted publisher setup (one-time)

The `release.yml` workflow publishes to PyPI via OIDC, so no API token is
stored anywhere. Setup only needs to happen once per PyPI project:

1. Reserve `mcp-server-roboflow` on [pypi.org](https://pypi.org/) under a
   maintainer account (already done for the initial release).
2. On the project's Settings -> Publishing page, add a GitHub trusted
   publisher with:
   - Owner: `MayankD409`
   - Repository: `Roboflow-MCP-Server`
   - Workflow: `release.yml`
   - Environment: `pypi`
3. The workflow targets the `pypi` environment so you can optionally add
   required reviewers in GitHub repo settings for an extra approval gate
   on every publish.

If publishing to TestPyPI as a dry run, duplicate the step in `release.yml`
with `repository-url: https://test.pypi.org/legacy/` and a second trusted
publisher registration on TestPyPI.
