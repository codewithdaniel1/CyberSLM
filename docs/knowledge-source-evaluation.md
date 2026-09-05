# Additional knowledge-source evaluation

Status: complete as of 2026-09-05.

This review closes the current source-discovery phase. It covers the eight credible source
families most likely to add value beyond CyberSLM's pinned ATT&CK, CWE, and CAPEC snapshots.
It is not a claim that every cybersecurity feed on the internet was reviewed. New candidates
should only reopen discovery when a concrete product gap cannot be met by the sources below.

## Decision criteria

A source was assessed for:

- unique value over ATT&CK, CWE, and CAPEC;
- an authoritative publisher and a stable, machine-readable schema;
- an immutable release or commit that can be pinned, hashed, and reconstructed;
- license and attribution obligations for local use and redistribution;
- update cadence, size, and risk of stale answers;
- suitability for semantic RAG versus exact or live structured lookup;
- noisy, operational, or potentially unsafe content; and
- a measurable held-out retrieval and answer-quality improvement.

`Adopt` means approved for a bounded implementation pilot, not automatically approved for the
production index. `Defer` identifies the product condition that would make the source useful.

## Decision matrix

| Source | Decision | Best integration | Rationale and conditions |
| --- | --- | --- | --- |
| [OWASP Cheat Sheet Series](https://github.com/OWASP/CheatSheetSeries) | **Retrieval passed provisionally; admission pending** | Curated, pinned prose RAG | Adds practical prevention and remediation guidance that CWE definitions do not provide. The opt-in pilot imports 24 allowlisted Markdown documents at commit `1eacf6cb9bfcba006ca972a804c5faace8c2758a`, retaining title, canonical URL, revision, and attribution. Its pending-review source-specific slice retrieves 24/24 intended documents with lexical and hybrid search, versus 0/24 without OWASP. The content is [CC-BY-SA-4.0](https://github.com/OWASP/CheatSheetSeries/blob/master/LICENSE.md); preserve its notice and attribution, and review share-alike handling before distributing derived content. |
| [MITRE D3FEND](https://github.com/d3fend/d3fend-ontology) | **Adopt second** | Pinned defensive-technique RAG | Adds defensive techniques, digital artifacts, and ATT&CK relationships. Import released ontology artifacts rather than scraping the website, and expose only concise technique definitions and relationships. The repository uses the [MIT license](https://github.com/d3fend/d3fend-ontology/blob/master/LICENSE.md) and also identifies D3FEND/ATT&CK trademark and terms notices that must be retained. |
| [CISA Known Exploited Vulnerabilities](https://github.com/cisagov/kev-data) | **Adopt third** | Exact-CVE local lookup, then optional RAG context | Adds authoritative evidence that a CVE has been exploited in the wild. Use the official JSON/schema and route only exact CVE or vulnerability-prioritization questions. The official mirror is updated shortly after the canonical catalog and is [CC0-1.0](https://github.com/cisagov/kev-data/blob/develop/LICENSE). Label remediation due dates as federal civilian agency requirements rather than universal deadlines. |
| [NVD](https://nvd.nist.gov/vuln/data-feeds) | **Defer bulk ingestion** | Future exact-CVE enrichment | The CVE/CPE APIs and feeds are useful, but a full semantic index would be large, fast-changing, and duplicative of KEV/OSV/CWE. Prefer a dated, on-demand lookup if the product later needs CVSS, CPE, or NVD enrichment. NIST information is generally public information, subject to the publisher's [copyright and data disclaimers](https://www.nist.gov/copyrights-disclaimers). |
| [OSV.dev](https://google.github.io/osv.dev/) | **Defer aggregate ingestion** | Future package/SBOM lookup | Its ecosystem-aware affected-version schema is valuable when users provide a dependency, manifest, or SBOM. The aggregate is continuously updated and its [upstream data sources have different licenses](https://google.github.io/osv.dev/data/), so do not treat the infrastructure's Apache license as a blanket data license. A future integration needs an ecosystem allowlist, per-record provenance, and license preservation. |
| [Sigma rules](https://github.com/SigmaHQ/sigma) | **Defer until detection-engineering mode** | Dedicated rule search/filter tool | More than a prose corpus, Sigma is executable detection logic whose usefulness depends on log source, product, rule status, and false-positive context. Its current schema exposes stable/test/experimental/deprecated statuses. Rules use [DRL-1.1](https://github.com/SigmaHQ/Detection-Rule-License), which requires author attribution, including for displayed matches. Do not mix rules into default semantic RAG. |
| [FIRST EPSS](https://www.first.org/epss/) | **Defer as live data** | Dated exact-CVE API/CSV lookup | EPSS is a daily probability signal, not durable prose and not a complete risk score. Embedding it would create stale answers. A future vulnerability-prioritization tool should fetch or snapshot the score, percentile, score date, and model context; the [official API/data guidance](https://www.first.org/epss/data) distinguishes lookup from bulk access and requests attribution. |
| [NIST OSCAL control catalogs](https://github.com/usnistgov/oscal-content) | **Defer until compliance mode** | Exact-control and profile lookup | The structured SP 800-53 catalogs and baselines are high quality but broad and organization-dependent. Adding them to default RAG would increase irrelevant prescriptive context. Revisit with an explicit governance/compliance mode. The official OSCAL content is public domain in the US and dedicated worldwide under [CC0-1.0](https://github.com/usnistgov/oscal-content/blob/main/LICENSE.md). |

## Approved implementation order

1. OWASP Cheat Sheet Series. Its pinned, opt-in parser and provisional retrieval A/B are
   complete. Project-owner label review, routing, and attribution checks remain before admission.
2. MITRE D3FEND, because it fills the defensive-countermeasure gap while connecting naturally
   to the existing ATT&CK source.
3. CISA KEV, as an exact-CVE prioritization lookup instead of a corpus searched for every
   message.

The other five sources are evaluated and intentionally deferred. They do not remain as
unresolved source-research work.

## Admission gate for each approved source

Before an approved pilot is added to `src/cyberslm/knowledge/sources.py`, it must have:

1. an immutable upstream release or commit, expected SHA-256, and expected document count;
2. a stored license/attribution notice and provenance on every indexed document;
3. schema validation, bounded parsing, duplicate handling, and failure-preserving sync tests;
4. at least 20 new held-out cases covering positive retrieval, abstention, conflicts, exact
   identifiers, attribution, and source-specific edge cases;
5. an A/B comparison against the existing three-source index; and
6. no regression in routing precision, citation/source attribution, safety, or answer quality.

Admit the source only if it adds measurable value. Otherwise record the pilot result here and
leave it disabled. This keeps source selection complete without assuming that more indexed
documents necessarily improve the model.

## What remains

The knowledge-source **selection evaluation is complete**. The remaining knowledge work is
implementation and empirical admission testing for the three approved pilots, one source at a
time. Model behavior evaluation, adapter experiments, and cross-platform runtime work remain
separate roadmap tracks; they do not require further source discovery.
