# HASP — Backlog Decomposition Benchmark

> **For the research agent:** This is a self-contained specification. Read, execute, iterate. No further context needed.

**Goal:** Design and benchmark an algorithm that decomposes a software backlog (precedence DAG) into feature-coherent groups, using Jira Components as ground truth.

**Research question:** Can community detection on transitively-closed dependency DAGs recover Jira Component assignments better than chance, and what pipeline configuration maximizes agreement?

**Output:** Ranked leaderboard of configurations, optimal pipeline, paper-ready figures (ARI/NMI/closure/entropy vs config parameters).

---

## 1. Dataset — TAWOS

**Source:** SOLAR-group/TAWOS (MSR 2022), download from [doi:10.5522/04/21308124](http://doi.org/10.5522/04/21308124)

**What it is:** 458,232 Jira issues across 39 open-source projects (Apache, Atlassian, MongoDB, Hyperledger, etc.). MySQL dump, ~2GB.

**Why it fits:**

| Benchmark need | TAWOS table.column | Notes |
|---|---|---|
| Dependency DAG | `Issue_Link`: name IN ('Blocks','Depend') + direction | INBOUND="is blocked by", OUTBOUND="blocks". Model as directed edge: source → target when source depends on target. |
| Ground truth communities | `Issue_Component` → `Component.Name` | Jira Components are feature areas. Many-to-many; filter to issues with exactly 1 component for clean evaluation. |
| Node attributes | `Issue.Story_Point`, `Issue.Priority`, `Issue.Title`, `Issue.Description_Text` | Priority is named (Blocker/Critical/Major/Minor/Trivial). Map to numeric: Blocker=5, Critical=4, Major=3, Minor=2, Trivial=1. |

**Setup steps:**

1. Install MySQL 8.0+
2. Download the `.sql` dump from UCL repository
3. Import: `mysql -u root -p TAWOS < tawoS_dump.sql`
4. Run extraction queries (see below)

**Extraction query per project** (`{project_key}` is e.g. `MESOS`, `FAB`, `SERVER`):

```sql
-- Get all issues for a project with their component (ground truth)
SELECT 
    i.ID, i.Issue_Key, i.Title, i.Description_Text, 
    i.Priority, i.Story_Point, i.Type, i.Status,
    c.Name AS component_name
FROM Issue i
JOIN Project p ON i.Project_ID = p.ID
LEFT JOIN Issue_Component ic ON i.ID = ic.Issue_ID
LEFT JOIN Component c ON ic.Component_ID = c.ID
WHERE p.Project_Key = '{project_key}'
  AND i.Type IN ('Story', 'Bug', 'Task', 'Improvement', 'New Feature')
  AND i.Status NOT IN ('Closed', 'Resolved', 'Done')  -- optional: active issues only
  AND i.Story_Point IS NOT NULL                         -- optional: need SP for later phases
ORDER BY i.ID;

-- Get dependency links for the project
SELECT 
    il.Issue_ID, il.Target_Issue_ID, il.Name, il.Direction
FROM Issue_Link il
JOIN Issue i ON il.Issue_ID = i.ID
JOIN Project p ON i.Project_ID = p.ID
WHERE p.Project_Key = '{project_key}'
  AND il.Name IN ('Blocks', 'Depend')
ORDER BY il.Issue_ID;
```

**Cleanup rules:**

1. Filter to issues with exactly 1 component (clean ground truth)
2. Map priorities to numeric (Blocker→5, Critical→4, Major→3, Minor→2, Trivial→1)
3. Build DAG: for each `(issue_id, target_id)` link where Direction='OUTBOUND' (issue blocks target), add edge `issue → target` (issue depends on target). For INBOUND, reverse.
4. For issues with zero incoming or outgoing dependency edges: keep them as isolated nodes. They still participate in clustering.
5. Remove projects with < 50 issues or < 3 components (too small for meaningful clustering)

**Expected output per project:** One CSV with columns `issue_id, title, priority, story_points, component` + one edge list `source_id, target_id`.

---

## 2. Algorithm Pipeline

The pipeline takes a DAG of issues and produces K feature groups. Stages:

### Stage 0: DAG preprocessing

```
Input: (nodes, edges)
Output: (nodes, augmented_edges)
```

**Operations:**
- `transitive_closure`: bool. If True, compute transitive closure of the DAG and add all transitive edges. Rationale: A→B→C means A and C are in the same feature; without transitive edges, clustering fragments long chains.
- `shared_parent_edges`: bool. If True, for every pair of child nodes sharing a parent, add a synthetic edge with weight `shared_parent_weight` (default 0.5). Rationale: siblings in the DAG are likely co-located features.
- `edge_weighting`: map. Link type → weight. Default: `{Blocks: 2.0, Depend: 1.0}`.

Implementation note: transitive closure on graphs with N ≤ 5000 nodes is O(N³) worst-case with Floyd-Warshall, but sparse DAGs do much better with BFS from each node (O(N(N+E))). For larger projects, sample or use a depth-bounded closure (max path length 3).

### Stage 1: Community detection

```
Input: (nodes, augmented_edges)
Output: partition → {node_id: cluster_id}
```

**Algorithm:** Leiden (preferred over Louvain — better guarantees on well-connected communities).

**Resolution tuning:**
- Parameter γ (resolution): default 1.0, sweep range [0.1, 5.0]
- Target: produce K clusters where K ∈ [min_k, max_k]
- Binary search on γ: run Leiden, count clusters, adjust γ, repeat (max 10 iterations)
- If target range is unreachable after 10 iterations, record K achieved and note failure mode

**Consensus clustering:**
- `ensemble_runs`: int (default 20). Run Leiden N times with different random seeds.
- Build co-occurrence matrix C where C[i][j] = fraction of runs where nodes i and j are in the same cluster.
- Run Leiden on C (threshold: C[i][j] ≥ `consensus_threshold`, default 0.5) to produce final partition.

### Stage 2: Cluster scoring and ranking

```
Input: (nodes, edges, partition)
Output: ranked_clusters → [{cluster_id, name, score, nodes, metrics}]
```

**Per-cluster metrics:**
- `dependency_closure`: internal_deps / total_deps (deps = edges where one endpoint is in this cluster)
- `size`: number of nodes
- `avg_priority`: mean priority of nodes in cluster
- `total_story_points`: sum of story points

**Composite score for ranking:**
```
score = α * avg_priority_norm + β * log(size) + γ * closure
```
Default: α=0.4, β=0.3, γ=0.3. Normalize avg_priority to [0,1] across all clusters.

**Top-K selection:** Present top 3–5 clusters (configurable).

### Stage 3: LLM labeling (optional, for presentation quality only)

```
Input: cluster → [{title, description_text, ...}]
Output: cluster_label → string (2–4 words)
```

Prompt template:
```
These Jira issues belong to the same feature area. Give this group a short, descriptive name (2-4 words max):

- {title_1}
- {title_2}
- ...

Name:
```

Use gpt-4o-mini or equivalent. One call per cluster, ~500 tokens each. Not required for benchmarking — labels affect presentation quality, not metrics.

---

## 3. Benchmark Design

### Independent variables (sweep space)

```yaml
transitive_closure: [true, false]
shared_parent_edges: [true, false]
shared_parent_weight: [0.3, 0.5, 0.7]
edge_weights:
  - {Blocks: 1.0, Depend: 1.0}        # uniform
  - {Blocks: 2.0, Depend: 1.0}        # weighted blocks
  - {Blocks: 3.0, Depend: 1.0}        # heavily weighted blocks
resolution_target:
  - {min_k: 3, max_k: 10}
  - {min_k: 5, max_k: 15}
  - {min_k: 10, max_k: 25}
  - {min_k: 15, max_k: 40}
  - null  # use default γ=1.0, no search
ensemble_runs: [1, 10, 20, 50]
consensus_threshold: [0.3, 0.5, 0.7]
cluster_scoring:  # for α,β,γ
  - {alpha: 0.4, beta: 0.3, gamma: 0.3}  # balanced
  - {alpha: 0.6, beta: 0.2, gamma: 0.2}  # priority-heavy
  - {alpha: 0.2, beta: 0.4, gamma: 0.4}  # closure-heavy
```

**Total combinations:** 2 × 2 × 3 × 3 × 5 × 4 × 3 × 3 = **6,480 configs**. At ~5 seconds per config × 39 projects, that's ~350 hours.

**Strategy:** Don't run full grid. Use the research agent to do intelligent search:
1. Phase 1: run 200 random configs across all projects, identify top-10 configurations
2. Phase 2: grid-search locally around top-10 (vary one parameter at a time)
3. Phase 3: final benchmark of best-3 configs against baselines

### Baselines

1. **Random:** shuffle component labels (permutation test for significance)
2. **No augmentation:** Leiden on raw DAG edges only, γ=1.0, no consensus
3. **Spectral clustering:** on adjacency matrix, K=ground truth component count (oracle K)
4. **Label propagation:** with known components as seeds (semi-supervised upper bound)

### Dependent variables (metrics)

| Metric | Formula | Range | Target |
|---|---|---|---|
| ARI | Adjusted Rand Index vs component labels | [-1, 1] | Maximize |
| NMI | Normalized Mutual Information vs component labels | [0, 1] | Maximize |
| Dependency Closure | mean(internal_deps/total_deps per cluster) | [0, 1] | Maximize |
| Cluster Entropy | Normalized Shannon entropy of cluster sizes | [0, 1] | Maximize (~1 = balanced) |
| Runtime | Wall clock seconds | [0, ∞) | Minimize (but not primary) |

**Composite objective (single number to rank configs):**
```
overall_score = 0.35 * ARI + 0.35 * NMI + 0.15 * closure + 0.15 * entropy
```

ARI and NMI are weighted higher because they measure agreement with ground truth.

### Statistical rigor

- Report mean ± std across 39 projects for each metric
- Friedman test with Nemenyi post-hoc to rank configurations
- Critical difference diagrams for top-10 configs
- Per-project breakdown: which projects are "easy" vs "hard" for the algorithm?

---

## 4. CLI Interface

```bash
# Single config run
python bench_decomp.py \
  --project MESOS \
  --config experiments/config_042.yaml \
  --output results/MESOS/run_042.json

# Batch run
python bench_decomp.py \
  --all-projects \
  --config experiments/config_042.yaml \
  --output-dir results/

# Sweep from config space
python bench_decomp.py \
  --all-projects \
  --sweep experiments/sweep_space.yaml \
  --samples 200 \
  --output-dir results/

# Generate leaderboard
python bench_decomp.py \
  --leaderboard results/ \
  --top 10 \
  --output results/leaderboard.json
```

### Config YAML format

```yaml
# experiments/config_042.yaml
pipeline:
  transitive_closure: true
  shared_parent_edges: true
  shared_parent_weight: 0.5
  edge_weights:
    Blocks: 2.0
    Depend: 1.0
  algorithm: leiden
  resolution_search:
    target_min_k: 5
    target_max_k: 15
  ensemble_runs: 20
  consensus_threshold: 0.5
  cluster_scoring:
    alpha: 0.4
    beta: 0.3
    gamma: 0.3
  min_closure_threshold: 0.5
  top_k_present: 5

baselines:
  - random
  - no_augmentation
  - spectral_oracle_k
```

### Output JSON format

```json
{
  "config_id": "042",
  "project": "MESOS",
  "pipeline": { ... },
  "results": {
    "ari": 0.62,
    "nmi": 0.58,
    "closure": 0.78,
    "entropy": 0.81,
    "composite": 0.65,
    "k_achieved": 8,
    "runtime_seconds": 3.2,
    "n_nodes": 847,
    "n_edges": 1203,
    "n_components_ground_truth": 6,
    "per_cluster": [
      {"id": 0, "size": 45, "closure": 0.91, "avg_priority": 3.2, "total_sp": 234},
      ...
    ]
  },
  "baselines": {
    "random": {"ari": 0.01, "nmi": 0.02},
    "no_augmentation": {"ari": 0.38, "nmi": 0.35},
    "spectral_oracle_k": {"ari": 0.44, "nmi": 0.41}
  }
}
```

---

## 5. Implementation Modules

```
experiments/
├── extract_taWOS.py          # MySQL → per-project CSV + edge list
├── pipeline/
│   ├── __init__.py
│   ├── dag_builder.py        # Load CSV+edges → NetworkX DAG
│   ├── preprocessing.py      # Transitive closure, shared-parent edges
│   ├── clustering.py         # Leiden wrapper, γ-search, consensus
│   ├── scoring.py            # Closure, entropy, ranking
│   └── labeling.py           # LLM labeling (optional)
├── metrics.py                # ARI, NMI, closure, entropy, composite
├── baselines.py              # Random, no-aug, spectral, label-prop
├── bench_decomp.py           # CLI entrypoint
├── configs/
│   ├── sweep_space.yaml      # Full parameter grid
│   └── baseline.yaml          # Minimal comparison config
└── results/
    ├── leaderboard.json       # Generated after sweep
    └── figures/               # Paper-ready plots
```

**Dependencies:** Python ≥3.10, networkx, igraph (for Leiden), scikit-learn (ARI/NMI), numpy, pandas, PyYAML, mysql-connector-python.

---

## 6. Execution Plan for Research Agent

### Phase 1: Setup (one-time)
1. Download and import TAWOS dataset
2. Run `extract_taWOS.py` for all 39 projects
3. Filter: exclude projects with <50 issues or <3 components
4. Record dataset statistics: {project, n_issues, n_edges, n_components, density, diameter}

### Phase 2: Random sweep
1. Sample 200 random configs from sweep space
2. Run each config against all qualifying projects
3. Compute per-project and aggregate metrics
4. Output: `leaderboard_phase2.json` — top 10 configs ranked by composite score

### Phase 3: Local optimization
1. Take top-3 configs from Phase 2
2. For each, vary one parameter holding others fixed at best value
3. Identify parameter sensitivity: which knobs matter most?
4. Output: sensitivity plots, refined top-3

### Phase 4: Final benchmark
1. Run best-3 configs + baselines against all projects, 30 repeats with different seeds
2. Statistical tests: Friedman + Nemenyi
3. Critical difference diagram
4. Output: final leaderboard, paper-ready figures

### Phase 5: Report
Generate `BENCHMARK_REPORT.md`:
- Dataset summary
- Top-3 configurations with ARI/NMI/closure/entropy
- Comparison to baselines (with significance)
- Parameter sensitivity analysis
- Per-project breakdown: which projects were easy/hard and why
- Recommended optimal config for production use

---

## 7. Success Criteria

| Criterion | Threshold | Stretch |
|---|---|---|
| ARI vs random baseline | p < 0.001 (significant) | ARI > 0.6 |
| Improvement over no-augmentation | ARI increase ≥ 0.10 | ARI increase ≥ 0.20 |
| Consensus over single-run | ARI increase ≥ 0.05 | ARI increase ≥ 0.10 |
| Runtime per project | < 30 seconds | < 10 seconds |
| Projects evaluable | ≥ 15 of 39 | ≥ 25 of 39 |

If no configuration significantly beats the no-augmentation baseline, the research contribution is a negative result: "dependency-aware preprocessing does not improve decomposition over raw Leiden on Jira issues" — still publishable.

---

## 8. Handoff Notes

- The algorithm is **unsupervised** — no training data, no labels at clustering time. Components are used only for evaluation.
- The output is a **decomposition**, not a selection. The optimizer that picks "which group to build this sprint" is separate and uses this as input.
- If TAWOS download is slow or MySQL import is problematic, fall back to a smaller public Jira dataset (any repo with 100+ issues and component labels will do for initial validation).
- The LLM labeling stage (Stage 3) is NOT required for benchmarking. Skip it in automated runs. It exists for the human-facing demo later.
- Save all intermediate results. The research agent may want to revisit configs after seeing initial results.

**Contact for questions:** The HASP team (via this workspace).
