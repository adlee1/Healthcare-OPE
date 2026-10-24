# Data access and repository boundaries

The clinical experiments use restricted derivatives of **MIMIC-IV 3.1**. The Git tree contains implementation code, synthetic test fixtures, and aggregate results. The complete restricted reproduction bundle is distributed separately through this private repository's Release **`baseline-data-2026-10-24`**, for members whose qualifications and access are covered by the authorization described below. A Git clone alone does not include the clinical inputs.

## Authorization and access scope

On **2026-10-24**, the repository owner confirmed that permission had been obtained to distribute the complete restricted bundle through this private GitHub repository and authorized that distribution. **Authorization basis: repository owner confirmation; no independent documentary verification was performed.**

Access is limited to qualified members covered by that confirmed permission. Private repository membership alone is not evidence of data eligibility. Keep the repository and Release private, and limit membership to the authorized recipients. This recorded confirmation applies to this project's specified bundle and distribution; it is not a general authorization to place other MIMIC-derived projects or data on GitHub.

The source data remain subject to applicable credentialing, training, data-use agreement, and institutional requirements. Source references are the [MIMIC-IV 3.1 project page](https://physionet.org/content/mimiciv/3.1/) and the [PhysioNet Credentialed Health Data License](https://physionet.org/about/licenses/physionet-credentialed-health-data-license-150/). This repository does not grant source-data credentials or extend the owner's confirmed permission to additional recipients or uses.

## Private Release assets

Release tag: **`baseline-data-2026-10-24`** in **`adlee1/Healthcare-OPE`**.

| Asset | Purpose |
|---|---|
| `APRIL_selected_baselines_20261023_English.zip` | Complete restricted reproduction bundle; **315,005,272 bytes** |
| `APRIL_selected_baselines_20261023_English.zip.sha256` | SHA256 checksum for the archive |
| `baseline-data-manifest.json` | Bundle scope, archive identity, and verification metadata |

Expected archive SHA256:

```text
886a6596ed255c863ade7094ec07e1a96c37cd81b7a47485e1c88fdc28ee16c2
```

The archive includes clinical features and outcomes, split assignments, validated annotation caches, original fitted models and paired bootstrap draws, and the source bindings needed for reproduction. Download and extract it only into approved storage outside the Git checkout. See [REPRODUCTION.md](REPRODUCTION.md) for authenticated download and verification commands. The original archive is preserved separately; this Release supplies the English README revision without changing scientific code or data.

## What stays out of the Git tree and collaboration surfaces

Do not commit or attach the following to the Git tree, issues, pull requests, or CI artifacts:

- Patient/event feature tables, outcomes, identifiers, cohort memberships, or split assignments.
- Patient-level prompts, provider responses, normalized annotation caches, or counterfactual labels.
- Bootstrap patient counts, per-draw records, or models fitted on the restricted clinical data.
- The restricted handoff bundle, its archive, or inventories exposing patient-level files. The specified private Release assets above are the authorized distribution channel.
- API keys, database credentials, `.env` files, or credential-bearing logs.

Credentials are excluded from Release assets as well. Re-encoding an identifier or removing direct identifiers does not change these boundaries. Keep new patient-level outputs in approved restricted storage; review aggregate results before adding them to the Git tree.

## Using an authorized local bundle

An appropriately authorized local bundle supplies the exact feature artifacts, validated annotation caches, original DM models and bootstrap draws, and provenance needed by the portable runner. Keep it outside the Git checkout in the institution's approved storage environment.

Run the repository entry point with `--package-root` pointing to that bundle. The runner resolves data and numerical source files relative to the bundle and checks their hashes. Historical absolute paths in original manifests are provenance only; the runner does not read from the original researcher's machine. See [REPRODUCTION.md](REPRODUCTION.md).

Both modes need this bundle:

| Mode | Required restricted material | What it does |
|---|---|---|
| `cached` | Original draw records, models, feature artifacts, and point/annotation artifacts | Verifies bindings and reconstructs statistics from stored draws |
| `fresh` | The same material, including complete clinical feature tables | Refits DM+ for selected original draw IDs; optionally also refits DM and the target policy |

Aggregate plotting is the data-free operation. It is different from `cached` statistical reconstruction.

The portable workflow uses already validated annotation caches. It makes no database queries or LLM API calls and does not revalidate the original provider response chain. Future label generation or new data extraction requires a separately authorized workflow; it is not enabled by obtaining this code repository.

## Local outputs

Treat fresh fitted models, draw outputs, and detailed local verification files as restricted. Write them to approved storage outside the checkout. Share only reviewed aggregate results through the repository. Git ignore rules reduce accidental inclusion but do not replace review of the actual staged files.

The attached archive is preserved byte-for-byte. Its README predates this release and states the earlier default restriction against GitHub uploads; the owner-confirmed exception above applies only to this private release.
