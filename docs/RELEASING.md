# Releasing

Short playbook for cutting a release. Maintainer only.

## Prep

1. Make sure `develop` is green: `make check`.
2. Branch off `develop`:
   ```bash
   git checkout develop && git pull
   git checkout -b release/x.y.z
   ```
3. Bump the version in **two** places (they must match):
   - `pyproject.toml` -> `[project] version = "x.y.z"`
   - `src/roboflow_mcp/__init__.py` -> `__version__ = "x.y.z"`
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
3. Creates a GitHub Release with auto-generated notes and attaches the
   artifacts.

## Close out

Back-merge `main` into `develop` so the merge commit and tag show up on
`develop` too:

```bash
git checkout develop && git pull
git merge --no-ff main -m "chore: back-merge vx.y.z into develop"
git push
```

## Delete the release branch

Once `main` and `develop` both contain the release merge, delete the branch:

```bash
git branch -d release/x.y.z
git push origin --delete release/x.y.z
```

(If branch protection auto-delete is on, the remote branch goes away on
merge and only the local delete is needed.)

## PyPI publishing (not yet wired up)

v0.1.0 ships as a GitHub Release only. To enable `pip install mcp-server-roboflow`:

1. Reserve `mcp-server-roboflow` on [pypi.org](https://pypi.org/) under a
   maintainer account.
2. Configure a [trusted publisher](https://docs.pypi.org/trusted-publishers/)
   on PyPI pointing at this repo's `release.yml` workflow. No API token
   needed; PyPI verifies against GitHub's OIDC.
3. Add a step to `release.yml`:
   ```yaml
   - uses: pypa/gh-action-pypi-publish@release/v1
   ```
4. Bump the `permissions` block to include `id-token: write`.

Keep this section until the PyPI flow is live; delete it after.
