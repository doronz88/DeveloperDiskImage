---
name: updating-xcode-ddis
description: Use when asked to "update ddis" / refresh the DeveloperDiskImage repository (doronz88/DeveloperDiskImage) from a newly installed Xcode, to bump or pin `LATEST_DDI_BUILD_ID` in pymobiledevice3, when pymobiledevice3 warns "Downloaded personalized image has unexpected ProductBuildVersion", or when asked whether a new Xcode DDI adds supported device models.
---

# Updating Xcode DDIs

Two repos move together: this one publishes the payloads, pymobiledevice3 (checkout assumed at `~/dev/pymobiledevice3`) pins the build id it expects. **Report the model-list diff to the user before creating a branch or writing anything** — it decides whether the update ships.

## Steps

1. **Sync, read-only.** `git fetch --prune origin` in both repos. Local `main` may be months stale; every baseline below is `origin/main`.
2. **Model-list diff (required):**
   `python3 .claude/skills/updating-xcode-ddis/ddi_model_diff.py` (from this repo's root)
   First line shows `<published build> -> <Xcode build>`. Same build → nothing to do, say so and stop.
3. **Prior attempts:** `gh pr list --state all --search '<build>'` in both repos.
4. **Tell the user**, verbatim from the diff output: old → new build, added/removed `SupportedProductTypes`, added/removed boards — also when it is all "none" — plus any prior PR for this build and how it ended.
   If no model was added, or a prior PR for this build was closed unmerged, ask whether to proceed and stop until answered. A no-new-models update has been declined before (PRs opened, then closed).
5. **Branch from `origin/main`:** `git checkout -b bugfix/image-<build> origin/main --no-track`. Name taken by an earlier attempt → `git log origin/main..<branch>` to see what it holds, tell the user, and let them pick reuse or delete; do not `-B`/`-D` it silently.
6. **Refresh payloads with the repo's script — never copy files by hand:**
   `uv run --script update_ddi.py` from the repo root (`--dry-run` to preview). It publishes both `Personalized` and `Cryptex` variants, verifies SHA-384 digests, and rewrites `Info.Path` to the fixed `Image.dmg*` names. Expect 8 changed files; "Wrote 0" means the branch already held this build.
7. **DDI PR:** `git add PersonalizedImages`; `git commit -m 'maintenance: Update DDIs to `<build>`'` (single quotes — the title contains backticks); push; `gh pr create --base main`.
8. **Pin PR in pymobiledevice3:** branch `feature/latest-ddi-<build>` from `origin/master`; set `LATEST_DDI_BUILD_ID` in `pymobiledevice3/services/mobile_image_mounter.py`; `uv run --no-sync pytest tests/services/test_cryptexd.py tests/test_tss_cryptex1.py` (bare `pytest`/`python3 -m pytest` lack the deps); `git add pymobiledevice3/services/mobile_image_mounter.py` only — the tree carries unrelated untracked files; commit/title `mobile_image_mounter: Bump version to `<build>``; `--base master`; body says it depends on the DDI PR.
9. **Merge order:** DDI PR first. pymobiledevice3 downloads from the DDI repo's `main` (`DEFAULT_REF` in `developer_disk_image/repo.py`), so a pin merged first mismatches what users download.
10. **Declined or closed:** `gh pr close` both, delete the remote branches, check out `main`/`master`, and list the leftover local branches for the user.

## Common mistakes

| Mistake | Consequence |
|---|---|
| Working on local `main` without fetching | Misses `update_ddi.py` / newer DDIs; diff computed against the wrong baseline |
| Copying `*.dmg` by hand | Manifest paths still point at `022-xxxxx-xxx.dmg`; Cryptex variant not updated |
| Branching or opening PRs before the model diff | User learns afterwards that nothing changed; PRs closed, stray branches left behind |
| Alarm at `sha384 ok, 122/140 identities` | Expected: the other identities declare a shorter, non-SHA-384 digest of the same file |
| `git add -A` | Sweeps unrelated untracked files into the PR |

`ddi_model_diff.py` reads the full Xcode manifest (Personalized and Cryptex identities both live in it). `--ref <git-ref>` compares against an older baseline; `--platform tvOS|watchOS|xrOS` for other DDIs (only iOS is published today).
