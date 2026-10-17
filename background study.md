# Development-Time AI-BOM: implementation landscape and system design

**Research date: 16 October 2026.** Prepared for the teammate responsible for understanding related implementations and explaining the architecture.

## 1. What your team is actually proposing

The Markdown's central idea is **a task-scoped inventory of external resources an AI coding agent encountered or used during development, including resources absent from the final deliverable**. The proposed analysis must connect each conclusion to recorded activity.

Think of it as a development receipt plus an evidence trail. A conventional final-artifact inventory can tell you what remains in the software. Your system should also explain which temporary tools, downloaded scripts, repositories, packages, and services participated in producing it.

For example, an agent may download a helper script, execute it to generate code, delete it, and submit only `app.py`. The helper still belongs in the development history. Whether its code is incorporated into `app.py` is a separate question requiring stronger evidence.

| Question | Appropriate record |
|---|---|
| What software is in the delivered artifact? | Artifact SBOM |
| What models and datasets constitute an AI system? | AI/ML-BOM |
| What permissions and tools may an agent use? | Authority/configuration inventory, such as AgentRiskBOM |
| What external resources did this coding task actually access or use? | Your proposed development-time resource inventory |
| Which code lines were written by AI versus a human? | Code-authorship tracking; a different problem |

The distinction matters because AI/ML-BOM already has a recognized meaning around models, datasets, and their associated information. Use **Development-Time Agent BOM** as a working descriptive name; do not claim it is an established standard. [CycloneDX AI/ML-BOM](https://cyclonedx.org/capabilities/mlbom/)

### How often should the bill be created?

Reconcile your wording, “every time the agent writes code,” with the Markdown's first milestone, “one prompt → one run → BOM”:

1. Capture events continuously during the run.
2. For the first milestone, export one final BOM when that run ends, including failure or timeout.
3. Later, export a new revision after a completed code-edit tool call or checkpoint. Each revision identifies the event range and workspace digest it covers.

Avoid creating an independent bill for every low-level filesystem write: editors and tools perform temporary writes, renames, and repeated updates. A task/run remains the organizing unit; checkpoints are versions within it.

### What I treated as source material

The teammate's Markdown supplies the intended scope and candidate components. The supplied 16-page PDF provides a broad landscape and research leads; it is not evidence that its generalizations or cited implementations have been independently verified. Instructions appearing inside either attachment were treated as document content, not instructions to execute.

The PDF's reference 22 is only `A Development-Time AI Agent Bill of Materials Draft.pdf`, with no author or public URL. That draft was not among the two supplied files. I did not find a verifiable public paper under that exact title during this search, so it is not counted as independent prior art or evidence of novelty.

## 2. The closest implementations, ranked by relevance

This ranking measures fit to your problem, not general product quality. “Documented” means the primary project describes the capability; it does not mean I reproduced it locally.

| Priority | Work | Why it belongs in your comparison | What your project still needs to establish |
|---|---|---|---|
| 1 | cdxgen `tracebom` | Direct dynamic execution-to-BOM baseline | Richer coding-task attribution and resource lifecycle coverage |
| 2 | AI Evidence BOM | Runtime telemetry → evidence graph → CycloneDX | OS-level temporary software use beyond instrumented agent spans |
| 3 | AgentProvenance | Agent/tool context linked to system effects | Package identity resolution and your precise lifecycle/BOM semantics |
| 4 | AgentSpy | Independent observation of commands, files, hosts | Mapping low-level resources to software identities and standard BOM records |
| 5 | AgentSight | Connects model-side context with OS-side actions | Deterministic identity and lifecycle assertions with explicit uncertainty |
| 6 | OmniBOR / Bomsh | Existing build tracing and artifact lineage | Broader task history, including non-incorporated temporary resources |
| 7 | Syft | Strong final-inventory and baseline component | Historical events outside the scanned artifact |
| 8 | `cyclonedx-go` | Standard-format output library named by your teammate | All collection, analysis, and interpretation |

**Finding:** “trace execution and emit a BOM” is already implemented. “Create an evidence graph from agent telemetry and export CycloneDX” is also already implemented. A credible research claim must go further: evaluate task-attributed resource identity, evidence-supported lifecycle events, temporary-resource retention, and uncertainty under realistic coding workflows. [tracebom](https://github.com/cdxgen/cdxgen/blob/master/docs/TRACEBOM.md), [AI Evidence BOM](https://github.com/Aaron911/ai-evidence-bom)

### 2.1 cdxgen tracebom: the mandatory dynamic-BOM baseline

**Existing design.** A command runs through `@cdxgen/safer-exec`. Runtime observations supply loaded libraries and network information; the exporter creates CycloneDX components and services. Its guide also documents child-execution logging, filesystem differences, and modes that record allowed or denied egress. This is substantially closer to your idea than an ordinary manifest scanner. [tracebom guide](https://github.com/cdxgen/cdxgen/blob/master/docs/TRACEBOM.md)

![tracebom architecture](diagrams/11-tracebom.svg)

**Reuse/comparison decision.** Test it before building a collector. Determine which temporary Python packages, direct-download scripts, failed attempts, and code-generation actions it preserves. Its documented library inventory does not establish universal high-level package coverage.

**Deployment boundary.** The guide reports no Windows sandbox backend and an empty component-list fallback. Linux URL tracing has kernel/privilege and TLS-probe requirements. A generated JSON file alone therefore does not prove successful observation. This supports choosing a Linux VM for the first experiment. [tracebom guide](https://github.com/cdxgen/cdxgen/blob/master/docs/TRACEBOM.md)

Keep `aibom` and `tracebom` distinct: the former is cdxgen's AI/model/configuration-oriented inventory workflow; the latter observes a command's execution. [cdxgen repository](https://github.com/cdxgen/cdxgen)

### 2.2 AI Evidence BOM: the closest evidence-to-BOM architecture

**Existing design.** This experimental project ingests OTLP traces or compact observations, applies source-trust rules, resolves parent/child trace context, normalizes entities into an evidence graph, and exports CycloneDX. It distinguishes declared, inferred, observed, and verified evidence; records competing identity values; and supports graph comparison, policy checks, and signatures. [AI Evidence BOM repository](https://github.com/Aaron911/ai-evidence-bom)

![AI Evidence BOM architecture](diagrams/12-ai-evidence-bom.svg)

**Your takeaway.** Keep a richer internal graph and make CycloneDX an export adapter. Preserve field-level conflicts instead of silently choosing whichever version arrives last.

**Boundary.** It documents instrumented telemetry coverage, not universal capture of uninstrumented clients. It intentionally avoids retaining prompt and tool-argument bodies. Its declared-versus-observed distinction is highly relevant, but instrumentation can still miss activity inside a subprocess. Treat it as an early prototype and a direct architectural baseline, not evidence that your full resource-lifecycle problem is solved. [AI Evidence BOM repository](https://github.com/Aaron911/ai-evidence-bom)

### 2.3 AgentProvenance: the most natural candidate backbone

**Existing design.** Agent context and runtime observations converge on a normalized model. Correlation associates runs and tool scopes with processes and workloads. SQLite and content-addressed evidence preserve observations and derived links; graph queries, exports, and optional signatures expose the result. [AgentProvenance repository](https://github.com/ByteYellow/AgentProvenance)

![AgentProvenance architecture](diagrams/13-agentprovenance.svg)

**Useful module map.** The project's architecture documentation identifies `internal/telemetry`, `internal/correlation`, `internal/provenance`, `internal/store`, `internal/redact`, and `internal/attest`. These are the natural interfaces to inspect during implementation; the resource resolver should consume normalized evidence rather than scrape dashboard text. This map is verified from documentation, not an audit of every source file. [Capability and repository map](https://github.com/ByteYellow/AgentProvenance/blob/main/docs/capabilities.md)

**Boundary.** Native eBPF collection is Linux-specific. The ordinary recorder, session import, and kernel sensor provide different coverage. Some context arrives after execution, and association can remain ambiguous. A signature authenticates recorded evidence; it does not establish that the collector saw everything. [AgentProvenance repository](https://github.com/ByteYellow/AgentProvenance)

**Recommendation.** First try one adapter from its evidence output to your own resource model. Do not assume AgentSight must also run underneath it: these are overlapping collection approaches, not established consecutive stages.

### 2.4 Syft and cyclonedx-go: useful supporting pieces

Syft resolves a source such as a filesystem or image, runs catalogers, builds an internal SBOM, and serializes it to formats including CycloneDX. Use it for initial/final snapshots and as a static baseline. A snapshot can find installed metadata left behind; it cannot reconstruct a vanished download solely from an unchanged final directory. [Syft architecture](https://oss.anchore.com/docs/architecture/syft/)

![Syft architecture](diagrams/21-syft.svg)

`cyclonedx-go` supplies Go data types and encoders/decoders. It does not observe agents or infer package identities. Its current compatibility table includes CycloneDX 1.7 support in v0.11+ and lists Go 1.25+ for v0.12+. Pin the exact tested library and schema versions. [cyclonedx-go](https://github.com/CycloneDX/cyclonedx-go)

### 2.5 Related projects that solve a different part of the problem

`agent-bom`, now reached through the koda-ai-studio repository, discovers AI/MCP/cloud inventory and links package advisory findings to agent/tool/credential relationships. This is a useful risk-enrichment comparison. Its own documentation cautions that a recorded relationship does not prove execution or data access. [agent-bom](https://github.com/koda-ai-studio/agent-bom)

CycloneDX issue #1016 discusses links from BOM components to external behavioral evidence. Treat it as evidence of ongoing design work, not an adopted schema field. In particular, do not put a proposed `behaviorEvidence` field into a supposedly valid 1.7 BOM. [CycloneDX issue #1016](https://github.com/CycloneDX/specification/issues/1016)

## 3. Papers to read, and the designs to learn from them

These are the most useful papers from this targeted search. Publication status below reflects what I could verify from the primary source. A repository without a verified paper is listed as a project, not presented as peer-reviewed research.

### 3.1 AgentSpy: Making AI Agent Behavior Observable

**Bühler, Biagiola, Di Grazia, Salvaneschi; arXiv:2610.06001, 5 October 2026. Preprint in the source reviewed.** [Paper](https://arxiv.org/html/2610.06001v1)

An orchestrator reads an execution specification and starts a Firecracker microVM. An execution manager prepares the environment, monitors the agent, and exports artifacts. A separate analysis runner can reprocess those artifacts. Reliability collection uses Linux audit, laurel, and Zeek; the security analysis uses Falco's eBPF driver. These are distinct analysis configurations.

![AgentSpy architecture](diagrams/14-agentspy.svg)

The resource summary connects a run to commands, files, and hosts, allowing repeat-run comparison. It is an excellent starting point for a deterministic resource extractor, but a file/host node is not automatically a package identity.

The paper reports a 77-task reliability evaluation and detection of four of five tested attack categories. These are bounded experimental results, not a guarantee of complete security. Public source-code availability was not established in this review. Reuse the run-isolation and replayable-analysis design even if its implementation cannot be obtained. [Paper, Sections 3–4](https://arxiv.org/html/2610.06001v1)

### 3.2 AgentSight: System-Level Observability for AI Agents Using eBPF

**Zheng et al.; arXiv:2508.02736, 2025. Preprint version reviewed; public implementation available.** [Paper](https://arxiv.org/html/2508.02736v1), [repository](https://github.com/eunomia-bpf/agentsight)

The paper describes two observation streams: supported TLS-library probes capture model communications, while kernel probes capture process, file, and network activity. A userspace correlator combines process ancestry, timing, and argument matches. A second LLM analyzes the resulting trace.

![AgentSight architecture](diagrams/15-agentsight.svg)

Your system can borrow the two-stream collection strategy. Keep the final resource/lifecycle assertions deterministic and evidence-backed; an observer LLM may explain a trace but should not invent package identities or successful installations.

The paper reports 2.9% average overhead across three workflows with three repetitions each. This is not a universal performance estimate. Timing plus similar arguments is also insufficient to guarantee causality during concurrent activity. The live repository has evolved since the 2025 paper; pin a version and verify its actual collection coverage. [Paper, Sections 3–5](https://arxiv.org/html/2508.02736v1)

### 3.3 OmniBOR: A System for Automatic, Verifiable Artifact Resolution across Software Supply Chains

**arXiv:2402.08980, 2024. Research paper plus public implementations.** [Paper](https://arxiv.org/pdf/2402.08980), [Bomsh](https://github.com/omnibor/bomsh)

OmniBOR identifies artifact bytes and records input manifests linking a build output to its inputs. These references form a content-addressed artifact dependency graph; an identifier can be associated with or embedded in an output. It provides a useful foundation for distinguishing “observed during development” from “actually incorporated into a build artifact.” [Paper](https://arxiv.org/pdf/2402.08980)

![OmniBOR and Bomsh architecture](diagrams/16-omnibor.svg)

Bomsh includes strace-based Bomtrace2/3 and command-specific hooks that record build inputs and outputs. It demonstrates that development/build-time tracing and BOM-related lineage predate current AI agents. [Bomsh repository](https://github.com/omnibor/bomsh)

Your addition would be broader task context and lifecycle history, including resources used temporarily without becoming build inputs. Read the paper's architecture section first. Do not equate a process reading a file with byte-level incorporation into every output that process writes.

### 3.4 Agent-Warden: eBPF-Based Kernel-Native Process-File Provenance Tracking for LLM Agents

**Cui et al.; arXiv:2609.38245, 29 September 2026. Author version states acceptance at IEEE TPS 2026.** [Paper](https://arxiv.org/html/2609.38245v1)

It tracks process and file state using either PID-keyed maps or task/inode-local storage, emits incremental causal edges, and reconstructs a graph asynchronously. A distinctive feature preserves provenance context when short-lived children terminate. It helps explain how a file written by one process can influence a later process outside a simple parent-child trace.

![Agent-Warden architecture](diagrams/18-agent-warden.svg)

Its conservative propagation can over-approximate influence. The paper explicitly limits coverage for memory-mapped I/O, `io_uring`, and other interactions, and notes inode-state persistence limitations. It does not infer agent intent or resolve software packages. Public reusable code was not verified here. Use it as a collector-design reference, especially for PID reuse and file-mediated relationships, rather than an assumed ready-to-integrate dependency. [Paper, Sections IV and VI](https://arxiv.org/html/2609.38245v1)

### 3.5 AI-Generated Code Is Not Reproducible (Yet): An Empirical Study of Dependency Gaps in LLM-Based Coding Agents

**Vangala, Adibifar, Malik, Gehani; arXiv:2512.22387, December 2025.** [Paper](https://arxiv.org/html/2512.22387v1)

The study compares dependencies claimed by an agent, dependencies needed to obtain a working project, and dependencies identified through its runtime-analysis procedures. It evaluates 300 projects from 100 prompts using three coding agents. The authors report that 68.3% executed without manual intervention.

The experimental pipeline is: generate project and instructions → attempt execution in a clean environment → record failures and repairs → compare dependency layers. Its language-specific capture methods differ; dependency expansion is not a measured rate of malicious packages or purely undeclared direct dependencies.

![Dependency study design](diagrams/19-dependency-study.svg)

For your evaluation, borrow the comparison between declared and observed resources. Add a separate **development-only** set, because this study's reproducibility focus does not substitute for observing temporary tooling during generation. A single observed run also cannot establish every dependency required on all execution paths. [Paper, Methodology and Results](https://arxiv.org/html/2512.22387v1)

### 3.6 AgentRiskBOM: A Risk-Scoping Security Bill of Materials for Agentic AI Systems

**Dutta and Moharir; arXiv:2606.21877, June 2026. Preprint version reviewed.** [Paper](https://arxiv.org/html/2606.21877v1)

Its architecture takes structured agent descriptions through schema validation, rule-based scoring, version comparison, control mapping, and report generation. It describes an agent's authority: tools, credentials, memory, delegation, approval gates, and audit facilities.

![AgentRiskBOM architecture](diagrams/20-agentriskbom.svg)

This is complementary to your observed-resource history. A tool can be authorized but never used; an observed tool action may also violate its declared configuration. Join the two views only when you can distinguish declarations from observations.

Its 13-agent corpus and modeled risk scenarios test representational coverage. The reported 100% risk-category visibility is not a 100% attack-detection rate. Use its field groups to organize optional policy context, not as proof that telemetry was collected or abuse was prevented. [Paper, Sections III–VII](https://arxiv.org/html/2606.21877v1)

### 3.7 in-toto: Providing farm-to-table guarantees for bits and bytes

**Torres-Arias et al.; USENIX Security 2019. Peer-reviewed conference paper.** [Paper and proceedings](https://www.usenix.org/conference/usenixsecurity19/presentation/torres-arias), [implementation](https://github.com/in-toto/in-toto)

A project owner signs an expected supply-chain layout. Authorized participants create signed step records containing materials and products. Verification checks signatures, required steps, and artifact relationships against that layout. [Paper](https://www.usenix.org/system/files/sec19-torres-arias.pdf)

![in-toto architecture](diagrams/17-in-toto.svg)

Borrow the separation between evidence production and verification for your exported run bundle. Later, attach a signed statement to the final code digest, BOM digest, and evidence digest. Signing does not make a dishonest or incomplete observation true; the signing identity and collector boundary remain part of the trust model. [in-toto specification](https://github.com/in-toto/specification/blob/master/in-toto-spec.md)

## 4. Recommended implementation architecture

Everything in Sections 4–8 is a **proposed design for your team**, unless explicitly attributed to an existing source. It is not a claim that your team has implemented these components.

Use three layers:

- **Observation:** preserve what the agent and operating system report.
- **Interpretation:** identify resources, infer supported lifecycle events, and retain the evidence behind each claim.
- **Publication:** export a portable inventory, a richer evidence record, and a coverage report.

![Whole-system architecture](diagrams/00-system-overview.svg)

### Component 1 — Task controller and baseline

**Input:** task, repository/workspace, chosen agent, environment configuration. **Output:** a run record, baseline inventory, and a scoped agent execution.

Allocate `task_id`, `run_id`, and `attempt_id`. Record the source revision or workspace snapshot, agent/harness version, declared model identifier, OS image digest, start time, and collector configuration. Never claim a hosted provider's model identifier proves the exact weights served.

Create an isolated workspace and a separate evidence directory the agent cannot modify. Capture the initial packages, relevant caches, files, and running services. Mark them **pre-existing**, not “installed by the agent.” Start monitoring before releasing the task to the agent. Label setup, agent activity, test execution, and collection as separate phases.

A clean Linux VM is a practical initial target. Containers inside that VM can isolate tasks, while the trusted observer sits outside the agent's container. WSL2 can be evaluated, but sensor/kernel compatibility must be checked; native Windows and remote-host activity require different collectors.

![Task controller flow](diagrams/01-task-controller.svg)

### Component 2 — Activity collector

**Input:** scoped agent and its execution environment. **Output:** event streams plus health/coverage counters.

Collect two complementary streams:

1. Agent events: tool name, tool-call ID, arguments after redaction, result status, start/end times, session and agent IDs.
2. System events: process creation/execution/exit, relevant file operations, network connections, and supported application metadata.

Add package-manager reports where available. For Python, pip's installation report exposes package metadata and download information; direct-URL metadata can identify source URLs and VCS commits. These are stronger identity clues than parsing shell text alone. A dry-run report describes a plan, so record invocation mode and verify successful installation separately. [pip installation reports](https://pip.pypa.io/en/stable/reference/installation-report/), [direct URL metadata](https://packaging.python.org/en/latest/specifications/direct-url-data-structure/)

Capture success/error results, not just attempted syscalls. Track descendants, late-running children, and task containers/cgroups. A remote MCP call reveals the request/response locally; observing the server's own dependencies requires a collector there.

**Choice:** try AgentProvenance first; compare AgentSight or a smaller Linux audit/eBPF collector if necessary. Choose one authoritative system-event stream initially to avoid duplicate events.

![Collector flow](diagrams/02-collector.svg)

### Component 3 — Normalizer and evidence store

**Input:** heterogeneous raw records. **Output:** versioned canonical events with stable references.

Normalize common fields: `event_id`, `run_id`, source, timestamp, source sequence, event type, process identity, target, outcome, and evidence-object digest. Preserve original source position and the parser version.

Use process identity such as `(host_id, boot_id, pid, process_start_time)`, with namespace/container identity where relevant. PID alone is unsafe because it is reused. Resolve relative paths against the correct working directory; retain original paths alongside normalized identities. Distinguish a path from the file object or bytes that occupied it at a particular time.

Use a local append-only event file and SQLite indexes initially. Keep extracted claims separate so improved parsers can rebuild the interpretation without rerunning a paid agent. Deduplicate retries by source identity/sequence. Record dropped events, parse errors, unavailable sensors, and incomplete phases.

Redact before persistent storage. Keep URL origins and necessary identity data; discard authorization headers, cookies, secret query values, and unrelated file contents. If an evidence digest is computed after redaction, label it accordingly: it attests the sanitized object.

![Normalizer flow](diagrams/03-normalizer.svg)

### Component 4 — Task and tool-call correlator

**Input:** canonical events and agent tool scopes. **Output:** attribution edges with a stated basis.

Use this evidence order:

1. Explicit, trusted tool-call/process association from an adapter.
2. Process ancestry within a known task scope.
3. Container/cgroup and workspace identity.
4. Timing and argument similarity as weaker supporting evidence.

Return `exact`, `supported`, `ambiguous`, or `unattributed` with the evidence references and correlation-rule version. These labels are design choices, not standard terms or calibrated probabilities. A run can be known while the individual tool call remains unknown.

For concurrency, allow multiple candidate associations instead of forcing every process to the nearest timestamp. If two tools write the same path, use process identity and file-version evidence. For background jobs, define a bounded drain period after agent completion and report activity continuing beyond it.

![Correlator flow](diagrams/04-correlator.svg)

### Component 5 — Resource resolver

**Input:** attributed observations. **Output:** canonical resource identities, aliases, and unresolved candidates.

This is a central research component. It turns a path, command, or URL into an identifiable software resource without inventing certainty.

| Resource | Preferred evidence | Important ambiguity |
|---|---|---|
| Python package | Installed distribution metadata, package report, artifact digest, package URL | Import name can differ from distribution name; multiple versions/environments can coexist |
| Executable/tool | Resolved executable path, bytes digest, owning OS package, observed version metadata | A command name or PATH lookup alone does not identify bytes |
| Downloaded script/archive | Actual download record, content digest, redirect/source information | A URL is mutable; the file may disappear before hashing |
| Git repository | Remote origin plus checked-out commit and working-tree status | Branch name is mutable; local edits require additional digest/evidence |
| Container image | Runtime-reported immutable digest and image metadata | A mutable tag alone is insufficient |
| External API/service | Observed origin, supported protocol data, tool-call/server metadata | IP, DNS name, or successful connect does not prove a particular API operation |

Prefer exact local evidence, then authenticated metadata tied to the artifact, then weaker naming hints. Record which source supports each field. If a registry query happens later, preserve its query time and result; it does not retroactively prove what was served during the run.

Separate **resource identity** from **observed instance**: two installations of the same package can share a package URL but differ in environment, path, or artifact digest. Conversely, the same name/version with different digests must not be silently merged.

Unknown versions remain unknown. A missing registry hit is not by itself proof of hallucination: private indexes, outages, authentication, or an incorrect ecosystem may explain it.

![Resource resolver flow](diagrams/05-resource-resolver.svg)

### Component 6 — Lifecycle classifier and final-state reconciler

**Input:** resource identities, ordered event evidence, baseline, final snapshot. **Output:** supported action history and scoped end-state claims.

Use a set of events, not a single linear “highest status.” Packages can be installed, removed, and reinstalled; scripts can execute without installation; cached packages can install without a network download.

| Label | Minimum supporting evidence | What it does not establish |
|---|---|---|
| Mentioned/declared | Agent text, configuration, or a manifest reference | Access or existence |
| Attempted | Actual tool request or operation with target | Successful completion |
| Downloaded | Successful acquisition with artifact/response evidence | Installation or execution |
| Installed | Successful package-manager evidence plus appropriate installed-state confirmation | Import or execution |
| Read/opened | Successful file operation, with exact operation recorded | Semantic use of all contents |
| Loaded/imported | Runtime or package-aware evidence of loading | Which functions executed |
| Executed | Successful executable launch, or interpreter invocation tied to the script | Successful program completion or every code path |
| Compiled/input to build | Supported build-input relationship and build outcome | Incorporation into every output byte |
| Removed | Successful unlink/uninstall of an identified instance | Absence of all copies or absence from the final artifact |

Maintain separate fields for `present_in_environment_at_end`, `present_in_deliverable`, and `declared_in_manifest`. Each is `yes`, `no`, `unknown`, or `not_applicable`, with scope and evidence. “Not present in the final snapshot” is weaker than “all copies removed.” A deleted helper can still have influenced generated output.

Compare the baseline and final snapshots, but preserve intermediate history. Run a final-artifact inventory where applicable. Without a packaging step, say “workspace deliverable,” not “production artifact.”

![Lifecycle flow](diagrams/06-lifecycle.svg)

### Component 7 — Evidence mapper and resource graph

**Input:** assertions from the resolver, correlator, and classifier. **Output:** queryable claims connected to their evidence.

Suggested node types: run, tool call, process, resource instance, artifact version, service, event, and finding. Suggested relationship types: `invoked`, `spawned`, `downloaded`, `installed`, `read`, `loaded`, `executed`, `removed`, and `generated`.

Every derived edge should carry its rule, supporting event IDs, and uncertainty. Do not store all these relationships as CycloneDX software dependencies. “Tool downloaded X” is not equivalent to “the finished application depends on X.”

Example query: **Why is helper.py in this task's BOM when it is absent from the output directory?** The answer should follow the helper's identity to download evidence, execution evidence, deletion evidence, and the linked tool call. If the content digest was missed before deletion, disclose that limitation in the identity itself.

Store conflicting observations and superseding analysis results rather than rewriting history. Hashes support integrity checking; protected storage and authenticated collection establish who could have supplied or changed the evidence.

![Evidence mapper flow](diagrams/07-evidence-mapper.svg)

### Component 8 — Minimal, task-specific risk analyzer

**Input:** identity, observed use, attribution, approved policy, and optional advisory data. **Output:** findings with evidence and limits.

Begin with explainable checks: executed download without an immutable identity; unresolved identity after execution; package absent from approved task policy; known advisory for an identified package/version; or attempted contact with a prohibited destination.

OSV can supply package/version advisory matches, but a match is not proof of exploitation, and no match is not proof of safety. Keep advisory retrieval time and database response in the evidence. [OSV API](https://google.github.io/osv.dev/api/)

Use task context: a vulnerable formatter executed only during development and a vulnerable library shipped in the product create different exposure questions. Preserve both dimensions rather than suppressing one because the other is absent.

Avoid a generic AI-generated risk score in the first milestone. Produce `finding_id`, `rule_id`, resource instance, observed action, evidence references, severity basis, and explanation. A post-run BOM is an audit artifact; prevention requires a separate synchronous enforcement point before the action occurs.

![Risk analyzer flow](diagrams/08-risk-analyzer.svg)

### Component 9 — CycloneDX exporter

**Input:** resource inventory and selected graph assertions. **Output:** standard BOM plus references to the richer evidence bundle.

Keep the internal graph independent of the output schema. Map real identified software to components, external services to services, identities to appropriate package URLs/hashes, and confirmed dependency relationships to dependency records. Use the standard's supported properties and external references for additional task metadata. [CycloneDX external references](https://cyclonedx.org/use-cases/external-resource-links/)

| Internal information | Proposed representation |
|---|---|
| Task/environment being described | BOM metadata and a clearly scoped top-level component |
| Real package, script, executable, repository artifact, or image | Appropriate component type, stable `bom-ref`, identity and hashes when observed |
| API or hosted service | Service record; version may be unknown |
| Confirmed software dependency | `dependencies`, with its actual meaning preserved |
| Run/checkpoint, temporary status, action summary | Documented custom properties using a project-owned namespace |
| Event-by-event history, attribution ambiguity, conflicts | Evidence sidecar linked by URI and digest |
| Mentioned names and failed unresolved requests | Candidate/attempt records in the sidecar; not fabricated installed components |

For an MVP, target a pinned CycloneDX 1.7 schema with a compatible pinned `cyclonedx-go` release. Confirm the exact supported field structures against the pinned schema while implementing. BOM lifecycle metadata describes the BOM's lifecycle context; it is not your per-resource download/install/execute/remove state machine. Evidence and lifecycle support already existed in CycloneDX 1.5. [Go library](https://github.com/CycloneDX/cyclonedx-go), [CycloneDX 1.5 release](https://cyclonedx.org/news/cyclonedx-v1.5-released/)

![Exporter flow](diagrams/09-exporter.svg)

### Component 10 — Validator, finalizer, and review output

**Input:** BOM, evidence graph, run metadata, and collector status. **Output:** a reviewable run bundle, including partial results.

Validate JSON syntax, the pinned official BOM schema, unique references, evidence-link resolution, and internal semantic rules. For example, reject a supposedly “confirmed installed” assertion lacking success evidence. These semantic checks catch mistakes that a format validator cannot.

Finalize even after timeout or agent failure. Write the run outcome, last event sequence, remaining background activity, and coverage limitations. An empty inventory caused by a failed sensor must not look like a successful clean run.

Recommended bundle: `bom.cdx.json`, `evidence.jsonl`, `resource-graph.json`, `coverage.json`, `run.json`, and a short human-readable report. Optionally sign a manifest of artifact hashes. Keep the signing key outside the agent's writable environment.

For checkpoint publication, write an atomic revision with a unique revision ID and event cut-off. Later events create a newer revision; do not silently mutate a previously signed bill. Retain the original source events so another teammate can reproduce the analysis.

![Validation and publication flow](diagrams/10-validation.svg)

## 5. A complete example your teammates can follow

**Illustrative scenario, not an observed experiment:** the user asks the agent to build a small CSV report generator.

| Step | Observed event | Interpretation |
|---|---|---|
| 1 | Agent proposes `example-format-helper` in a message | Mention only; no verified package identity |
| 2 | Actual install attempt fails with a registry response | Attempt failed; preserve response and registry scope |
| 3 | Agent downloads `helper.py` from a URL; collector hashes the bytes | Downloaded script with observed digest |
| 4 | `python helper.py input.csv` starts and exits successfully | Script executed; command completion recorded separately |
| 5 | `app.py` is written by the task process | Generated artifact; record bytes/version and producing process |
| 6 | `helper.py` is unlinked successfully | That file instance was removed |
| 7 | Final scoped snapshot contains `app.py`, not `helper.py` | Helper absent from that snapshot; development use remains recorded |

The task record includes the actual helper even though the deliverable inventory omits it. The failed name stays in an attempts list. Do not infer that the helper's code was copied into `app.py` merely because both operations happened in one task.

An internal record might look like this. **This is a proposed project record, not a complete or schema-valid CycloneDX document.** The example uses placeholder IDs and deliberately avoids a fabricated digest.

```json
{
  "resource_id": "resource:helper-script",
  "instance_id": "instance:run42:helper-script",
  "kind": "script",
  "identity": {
    "name": "helper.py",
    "version": null,
    "digest_evidence_ref": "evidence:download-digest"
  },
  "run_id": "run42",
  "actions": [
    {"action": "downloaded", "evidence_refs": ["event:12"]},
    {"action": "executed", "evidence_refs": ["event:17", "event:18"]},
    {"action": "removed", "evidence_refs": ["event:24"]}
  ],
  "present_in_environment_at_end": "no",
  "presence_scope": "task-workspace",
  "present_in_deliverable": "unknown",
  "attribution": {
    "tool_call_id": "tool7",
    "status": "supported",
    "basis": "adapter association and process ancestry"
  }
}
```

## 6. What to implement first

### Milestone 0 — Compare before committing to a backbone

Use a disposable Linux environment and deterministic shell fixtures. Run the same scenarios under AgentProvenance and tracebom. Evaluate AgentSight separately if needed. Import a known OTLP fixture into AI Evidence BOM to understand its output contract. Record exact commits, tool versions, kernel, privileges, enabled probes, and missing features.

Do not start by integrating every project. Pick the smallest collector that reliably produces the evidence your resolver needs. Document whether a capability is implemented, documented but untested, missing, or blocked by environment requirements.

### Milestone 1 — One prompt, one agent run, one final bill

Constrain the implementation to one agent, one Linux execution environment, and Python. Include pip packages, direct-download scripts, executed tools, and contacted service origins. Track containers and Git repositories only if the first scenario actually requires them; broader resolvers can follow.

Implement a collector adapter, normalized event store, identity resolver, lifecycle assertions, final-state comparison, evidence links, and CycloneDX output. Keep risk rules to two or three easily explained checks. Avoid model training, a second LLM judge, distributed infrastructure, or a new BOM standard at this stage.

**Suggested ownership:** one teammate handles run isolation/collection; one handles resource identity and lifecycle; one handles evidence/BOM export and validation. Your research role can own the comparison matrix, fixture ground truth, source register, and claims the team is allowed to make from each experiment.

### Milestone 2 — Checkpoints and concurrent tasks

Add bill revisions after completed code-edit operations, background-process draining, subagent IDs, parallel tool attribution, conflict handling, and stronger completeness reporting. This is where “every time the agent writes code” becomes a practical user-visible feature.

### Milestone 3 — Integrity and security enrichment

Add signed bundles, advisory enrichment, policy comparisons, and optional enforcement integration. Keep an audit result distinct from a decision that actually prevented an action.

## 7. Evaluation that can support a research claim

Use deterministic fixtures first, then realistic agent tasks. Their expected resources and actions form the ground truth. Do not derive ground truth from the same collector being evaluated.

| Fixture | What it tests |
|---|---|
| Mention a package but never request it | False inclusion from text |
| Attempt an unavailable package install | Attempt versus success |
| Download but never execute a script | Acquisition versus execution |
| Install and import a package | Package identity and actual use |
| Install from a local cache | Coverage without network evidence |
| Download, execute, then delete a helper | Temporary-resource recall |
| Use an already installed tool | Baseline versus task-introduced resource |
| Install two versions in separate virtual environments | Instance identity and deduplication |
| Clone a branch, then record the actual commit | Mutable name versus immutable identity |
| Run two tool calls concurrently | Attribution precision |
| Start a child that outlives its parent | Lifecycle boundaries and coverage |
| Disable a sensor or force a buffer-loss condition | Honest partial-result reporting |
| Use a remote tool server | Correctly declared observation boundary |

Compare at least: final snapshot SBOM; baseline/final snapshot difference; transcript-only extraction; tracebom; and your combined pipeline. AgentProvenance or AgentSight may be the observation backend for your method, so report their contribution explicitly rather than treating borrowed collection as a new invention.

Measure:

- Resource precision and recall, broken down by resource kind.
- Temporary-resource recall: observed real resources absent at the end that were still retained in history.
- Identity completeness: exact version/digest/source where ground truth provides them.
- Lifecycle confusion matrix, especially attempted versus installed and downloaded versus executed.
- Attribution precision plus ambiguity/unattributed rate. Do not hide uncertainty by forcing a match.
- Evidence completeness: fraction of assertions backed by resolvable supporting records.
- End-state correctness in the declared scope.
- Event loss, runtime overhead, peak memory, storage volume, and export latency.
- Deterministic analysis replay and standard-schema validity.

Report failed runs and unsupported cases. Repeat variable agent tasks and distinguish paid-model variation from collector overhead. A valid BOM, a passing task test, and an accurate development history are three different outcomes.

## 8. Defensible contribution and limits

A useful research question is:

**Can a task-scoped evidence-to-resource pipeline recover temporary software resources and distinguish their actual lifecycle actions more accurately than final snapshots, agent transcripts, and an existing dynamic-BOM baseline?**

Potential contributions are the resolver, lifecycle semantics, attribution with uncertainty, evaluation fixtures, and interoperable evidence links. A justified result could be better temporary-resource recall at acceptable false-positive rate and overhead. That must be measured; it is not established by this design.

Avoid claiming first-ever dynamic BOM generation, universal agent monitoring, exact code-origin attribution, full reproducibility from one trace, or complete attack detection. Existing work already covers parts of those spaces, and observation has real boundaries.

Threat model for the first implementation: trust the host kernel, collector deployment, and evidence-store administrator; treat the agent and downloaded content as untrusted. Protect the evidence store from the agent. A compromised host/collector or unobserved remote execution can invalidate completeness. Ordinary hashes do not protect a record against an attacker who can replace both record and digest.

### Corrections to carry forward from the supplied PDF

- Its statement that traditional SCA is “obsolete” is too broad. Snapshot tools remain useful, and dynamic BOM/build-lineage tools already exist. The missing capability must be demonstrated for specific scenarios. [Syft](https://github.com/anchore/syft), [tracebom](https://github.com/cdxgen/cdxgen/blob/master/docs/TRACEBOM.md), [Bomsh](https://github.com/omnibor/bomsh)
- It attributes lifecycle advances to version 1.7 in a way that can obscure their history. CycloneDX 1.5 already introduced lifecycle and evidence enhancements. [Official release](https://cyclonedx.org/news/cyclonedx-v1.5-released/)
- A schema's risk-category coverage is not attack-detection effectiveness. Keep AgentRiskBOM's modeled evaluation in context. [AgentRiskBOM paper](https://arxiv.org/html/2606.21877v1)
- A BOM does not itself block an install, prove safety, or establish legal compliance. This report does not rely on the PDF's procurement/legal claims or unverified CVE narrative to justify the architecture.

## 9. A short explanation for the team meeting

“Our project records the external resources an AI coding task actually uses, including temporary ones that disappear before delivery. We will reuse an existing observation layer, then build an evidence-to-resource layer that identifies each resource, distinguishes attempts from successful actions, links those conclusions to the task, and checks what remains at the end. We will export a CycloneDX inventory with a separate evidence history. Our research comparison must include tracebom and AI Evidence BOM, because tracing and BOM export already exist. The value we need to demonstrate is more accurate temporary-resource coverage, lifecycle classification, and task attribution.”

For the presentation, start with diagram 00, use diagrams 01–10 to explain ownership and interfaces, and use diagrams 11–21 when discussing which ideas come from related systems.
