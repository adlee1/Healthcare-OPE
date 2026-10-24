# Data access and repository boundaries

The clinical experiments use restricted derivatives of **MIMIC-IV 3.1**. This repository distributes implementation code, synthetic test fixtures, and aggregate results. It does not distribute the clinical data required to reproduce those results.

## What is excluded from GitHub

Do not commit or attach any of the following to this repository, its releases, issues, pull requests, or CI artifacts, including when the repository is private:

- Patient/event feature tables, outcomes, identifiers, cohort memberships, or split assignments.
- Patient-level prompts, provider responses, normalized annotation caches, or counterfactual labels.
- Bootstrap patient counts, per-draw records, or models fitted on the restricted clinical data.
- The restricted handoff bundle, its archive, or inventories exposing patient-level files.
- API keys, database credentials, `.env` files, or credential-bearing logs.

These are project release boundaries. Re-encoding an identifier or removing direct identifiers does not make a patient-level derivative suitable for this GitHub release.

## Accessing the source data

Obtain MIMIC-IV access through PhysioNet and comply with the applicable credentialing, training, data-use agreement, and institutional requirements. The authoritative source is the [MIMIC-IV 3.1 project page](https://physionet.org/content/mimiciv/3.1/), together with the [PhysioNet Credentialed Health Data License](https://physionet.org/about/licenses/physionet-credentialed-health-data-license-150/).

PhysioNet's MIMIC guidance treats derived datasets and models as sensitive and directs sharing through PhysioNet under the source-data agreement. Having individual access credentials does not, by itself, authorize arbitrary redistribution of a derived bundle. Consult the applicable PhysioNet and institutional process before arranging access to restricted derivatives. [MIMIC-IV guidance](https://physionet.org/content/mimiciv/3.1/).

This repository does not grant data access, provide a public download for the restricted bundle, or solicit patient data through GitHub.

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
