# Contributing to Music Tag Editor

Thanks for helping! Bug reports, ideas and pull requests are all welcome.

## Reporting bugs and requesting features

Use the [issue templates](https://github.com/midoreigh/MusicTagEditor/issues/new/choose).
For tag bugs, the output of `mte-cli dump <file>` for an affected file helps a lot.

## Development setup

You need [uv](https://docs.astral.sh/uv/). It installs the right Python (3.12) for you.

```bash
git clone https://github.com/midoreigh/MusicTagEditor.git
cd MusicTagEditor
uv sync              # creates .venv with the app and dev tools
uv run mte           # run the app
uv run pytest        # run the tests (GUI tests run headless)
```

On Ubuntu, Qt needs: `sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1`.

## How changes get in

`main` is protected: every change goes through a pull request, and the tests must pass
on Linux, Windows and macOS before it can be merged.

1. Create a branch from `main` with a short prefixed name:
   - `feat/…` for a new feature
   - `fix/…` for a bug fix
   - `docs/…` for documentation
   - `chore/…` for tooling, CI or dependencies
2. Make your change and add or update tests. `src/mte/core` has no Qt code and should
   be tested directly. UI behaviour goes in `tests/test_ui_smoke.py` and friends.
3. Run `uv run pytest` locally.
4. Add a line under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md) for anything
   users would notice.
5. Open a pull request. Its title becomes the commit message on `main` (PRs are
   squash-merged), so write it as a short imperative sentence, e.g. "Add folder tree
   to the left pane".

## Code layout

```
src/mte/core/      tag model, format adapters, editing session, naming (no Qt)
src/mte/ui/        PySide6 windows and dialogs
src/mte/cli.py     command line
packaging/         PyInstaller spec and installer scripts
tests/             pytest suite
```

Match the style of the code around your change. Tag edits must never silently drop
data: unknown frames and atoms are kept as they are unless the user deletes them.

## Releasing (maintainers)

1. On a branch, set the version in `src/mte/__init__.py` and `pyproject.toml`, then run
   `uv lock`.
2. In `CHANGELOG.md`, rename `[Unreleased]` to the new version with today's date, and
   add a fresh `[Unreleased]` section.
3. Merge that PR, then tag the merge commit on `main` and push the tag:
   `git tag v1.2.3 && git push origin v1.2.3`
4. The **Release** workflow checks that the tag matches the version, runs the tests,
   builds installers for every OS, and publishes a GitHub Release with that changelog
   section as its notes.

To try the packaging without releasing, run the **Release** workflow manually from the
Actions tab. The installers are attached to that run as artifacts, and nothing is
published.
