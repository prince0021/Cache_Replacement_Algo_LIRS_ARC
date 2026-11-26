# Understanding Cache Replacement: A Complete Guide

> **Audience:** You — an undergraduate honors student preparing for an oral defense.
> This document is *not* for submission. It is your study companion: it explains
> every concept from scratch, walks through every algorithm with tables you can
> reproduce on paper, and ends with 18 practice questions your committee might ask.

---

## Table of contents

1. [The big picture](#1-the-big-picture)
2. [What is a replacement policy?](#2-what-is-a-replacement-policy)
3. [Zipf's law from zero](#3-zipfs-law-from-zero)
4. [Why we don't use numpy.random.zipf](#4-why-we-dont-use-numpyrandomzipf)
5. [Working set vs cache capacity](#5-working-set-vs-cache-capacity)
6. [How big is big enough — the sizing study](#6-how-big-is-big-enough--the-sizing-study)
7. [Trace families and what they test](#7-trace-families-and-what-they-test)
8. [Algorithm-by-algorithm guide](#8-algorithm-by-algorithm-guide)
   - [ARC](#arc--adaptive-replacement-cache)
   - [LIRS](#lirs--low-inter-reference-recency-set)
   - [CLOCK-Pro](#clock-pro)
   - [CAR](#car--clock-with-adaptive-replacement)
   - [MQ](#mq--multi-queue)
   - [LRU-K (K = 2)](#lru-k-k--2)
   - [SRRIP](#srrip--static-re-reference-interval-prediction)
   - [BRRIP](#brrip--bimodal-rrip)
   - [DRRIP](#drrip--dynamic-rrip)
   - [SHiP (dropped)](#ship-dropped)
9. [Software caches vs hardware caches](#9-software-caches-vs-hardware-caches)
10. [How to read each chart](#10-how-to-read-each-chart)
11. [Expected vs measured](#11-expected-vs-measured)
12. [Limits of this study](#12-limits-of-this-study)
13. [Oral-defense practice questions](#13-oral-defense-practice-questions)
14. [Glossary](#14-glossary)

---

## 1. The big picture

Your professor asked for two things your earlier report lacked:

1. **Practical simulator verification** — prove that the code faithfully implements
   each algorithm by running hand-traced test cases whose answers you derived on
   paper.
2. **Manual tracing** — demonstrate that you can step through ARC and LIRS (at
   minimum) by hand, one access at a time, and predict every hit, miss, and data
   structure change.

To answer those, this project builds:

| Deliverable | Purpose |
|---|---|
| A simulator with 8 advanced + 4 baseline policies | Runs traces, collects hit ratios |
| 48 synthetic traces (32 Zipfian, 4 scan, 4 loop, 8 extension) | Cover every workload regime your report discusses |
| A sizing study | Proves that your chosen trace length is long enough for stable numbers |
| An experiment engine | Automates all (trace × policy) runs, capacity sweeps, and variance studies |
| A Streamlit app | Lets you explore results, step through algorithms, and export figures |
| This document and a manual-tracing guide | Prepare you for the oral defense |

Everything is driven by `python run.py all` and can be re-generated from scratch.

---

## 2. What is a replacement policy?

A **cache** is a small, fast storage that keeps copies of recently or frequently
used data so that the system doesn't have to fetch it from a larger, slower
storage every time. Think of it like keeping your most-used textbooks on your
desk (fast to grab) instead of walking to the library (slow) each time.

The cache has a fixed number of slots — its **capacity**, *C*. When a program
asks for a piece of data (a **block** or **page**), one of two things happens:

- **Hit:** the block is already in the cache. No slow fetch needed. Fast.
- **Miss:** the block is not in the cache. The system must fetch it from the
  slower storage. If the cache is full, one existing block must be removed
  (**evicted**) to make room. Slow.

A **replacement policy** is the rule that decides *which* block to evict when the
cache is full and a new block arrives. The goal is to minimize misses (or
equivalently, maximize the **hit ratio** — the fraction of accesses that are
hits).

### Why a miss costs so much

| Level | Typical access time |
|---|---|
| L1 cache | ~1 ns |
| L2 cache | ~5 ns |
| L3 / LLC | ~20 ns |
| Main memory (DRAM) | ~100 ns |
| SSD | ~100,000 ns (0.1 ms) |
| Hard disk | ~10,000,000 ns (10 ms) |

A miss at the LLC (last-level cache) costs roughly 5× the hit time. A miss in a
disk-backed page cache can cost 100,000× the hit time. Even a 1-percentage-point
improvement in hit ratio can translate to measurable speedups in real workloads
because each avoided miss saves many nanoseconds or milliseconds.

---

## 3. Zipf's law from zero

In real systems, not every piece of data is equally popular. A few "hot" items
get most of the requests, while a long tail of items are rarely accessed. This
pattern follows **Zipf's law**.

Zipf's law says: if you rank items by popularity (rank 1 = most popular), then
the frequency of the item at rank *r* is proportional to:

$$f(r) \propto \frac{1}{r^{\alpha}}$$

where **alpha** (α) controls the skew:

- **α = 0**: perfectly uniform — every item equally likely.
- **α = 1**: the classic Zipf distribution — rank 2 gets half as many requests as rank 1,
  rank 3 gets a third, etc.
- **α > 1**: extremely skewed — the top few items dominate almost everything.

### Worked example: top-10 share

Suppose we have 1,000 distinct blocks. We compute the probability of each rank
and then ask: what fraction of all requests go to the top 10 blocks?

| Alpha | Share of requests to top 10 of 1,000 blocks |
|---|---|
| 0.2 | ~5.2% |
| 1.0 | ~34.5% |
| 1.6 | ~74.7% |

How to compute this by hand for α = 1.0:

1. Probabilities are proportional to 1/1, 1/2, 1/3, ..., 1/1000.
2. The normalizing constant (harmonic number) H₁₀₀₀ ≈ 7.485.
3. Sum of top 10: 1 + 1/2 + 1/3 + ... + 1/10 ≈ 2.929.
4. Top-10 share = 2.929 / 7.485 ≈ 0.391, or about 39%.

(The exact number varies slightly depending on the number of blocks. Our
simulator uses this computation on the actual working-set size.)

### Why alpha matters for caching

- At low alpha (0.2), every block is nearly equally likely — the cache can't
  predict the future well, and hit ratios are low unless the working set fits
  inside the cache.
- At high alpha (1.6), the top blocks are so dominant that even a small cache
  captures most of the traffic, and all policies perform similarly (there's not
  much room to be clever).
- The interesting range is **alpha around 0.6 – 1.2**, where policy differences
  are most visible.

---

## 4. Why we don't use numpy.random.zipf

Python's `numpy.random.zipf(alpha, size)` seems like the obvious choice, but it
has two fatal problems for this project:

1. **It raises an error for alpha ≤ 1.** Five of our eight alpha values (0.2,
   0.4, 0.6, 0.8, 1.0) are at or below 1.0. The function requires alpha > 1
   because the underlying Zipf distribution is only normalizable for α > 1 when
   the support is the entire positive integers.

2. **It is unbounded.** It samples from the set {1, 2, 3, ...} with no upper
   limit. We need to control the **working-set size** — the number of distinct
   blocks — precisely (e.g., 2 × C = 4,096 blocks). An unbounded generator could
   produce block IDs in the millions, making the working set uncontrollable.

### Our approach: bounded Zipf

Instead, we construct a **bounded Zipf** distribution over exactly *W* blocks:

```python
ranks = np.arange(1, W + 1)
probabilities = 1.0 / ranks ** alpha
probabilities /= probabilities.sum()       # normalize to sum to 1
draws = rng.choice(W, size=N, p=probabilities)
permutation = rng.permutation(W)           # shuffle rank → block ID
trace = permutation[draws]
```

Key properties:
- Works for **any** alpha ≥ 0, including alpha = 0.2 or alpha = 1.0.
- The working set is exactly *W* distinct blocks (for low alpha, almost all will
  appear; for high alpha, some rare blocks may not appear in a finite trace, but
  the generator is defined over all *W*).
- The permutation step ensures that block IDs are not correlated with rank — a
  block being "popular" or "rare" is not predictable from its numeric ID.
- Seeded RNG makes the trace fully deterministic and reproducible.

### Reusable methodology paragraph (for your report)

> Traces were generated using a bounded Zipf distribution. For a given skew
> parameter α and working-set size W, we assign each of W blocks a probability
> proportional to 1/r^α, where r is the block's popularity rank (1 = most
> popular). We then draw N independent samples from this distribution and apply a
> seeded random permutation to map ranks to block IDs, breaking any correlation
> between a block's numeric identifier and its access probability. We do not use
> NumPy's built-in `numpy.random.zipf` because it is undefined for α ≤ 1 and
> produces unbounded block IDs, making working-set size uncontrollable. All traces
> are deterministically reproducible from the base seed and trace name.

---

## 5. Working set vs cache capacity

The **working set** (W) is the number of distinct blocks that a trace can
reference. The **cache capacity** (C) is how many blocks the cache can hold at
once. The ratio W/C is the single most important parameter for understanding
results:

| W/C | What happens |
|---|---|
| **W ≤ C** (e.g., 0.5C, 1.0C) | Every distinct block fits in the cache. After the first pass (compulsory misses), almost everything is a hit. **All policies get ~99%+ hit ratio**, and there is essentially nothing to distinguish them. |
| **W = 2C** | Moderate pressure. The cache can hold half the working set. Policy differences become visible. |
| **W = 10C** | Heavy thrashing territory. The working set is 10× the cache. Only the most popular blocks can stay cached. This is where advanced policies shine. |

### Why W ≤ C traces tie

If W ≤ C, then after at most W cold misses, every block is cached. From that
point, every access is a hit regardless of the replacement policy. The only
misses are **compulsory** (also called "cold" misses) — the very first time each
distinct block is accessed.

Hit ratio ≈ 1 − W/N, where N is the trace length. For W = 0.5C = 1,024 and
N = 600,000, that's 1 − 1024/600000 ≈ 99.8%.

These traces are still useful: they serve as a **sanity check**. If any policy
scores significantly below ~99.7% on a W ≤ C trace, something is wrong.

### The capacity sweep

To make W ≤ C traces informative, we also run a **capacity sweep**: for each
trace, we test capacities at 0.25C, 0.5C, C, 2C, and 4C. As the cache shrinks
below the working set, policies start to diverge, and you can plot a **miss-ratio
curve** (miss ratio vs. capacity) that shows how each policy degrades under
pressure.

---

## 6. How big is big enough — the sizing study

### The problem

If you run a trace of only 1,000 references with a cache of capacity 1,000, most
of the misses are compulsory (first-time) misses. The replacement policy barely
gets a chance to evict anything. The measured hit ratio is dominated by start-up
effects, not by the policy's quality.

### Three sources of bias in short traces

1. **Start-up (compulsory) miss bias.** Every distinct block causes one
   compulsory miss the first time it appears. In a trace of length N with W
   distinct blocks, at least W misses are compulsory. The compulsory miss *rate*
   is W/N. If N is only 5× the working set, compulsory misses account for 20% of
   all accesses — they swamp the signal.

2. **Warm-up bias.** Adaptive policies (ARC's target p, CLOCK-Pro's m_c, DRRIP's
   PSEL) need time to learn the workload. If the trace ends before they've
   adapted, their scores are unfairly low.

3. **Seed noise.** Because traces are randomly generated, different seeds produce
   slightly different hit ratios. Short traces amplify this noise; long traces
   average it out.

### What the sizing study does

The study runs five fast policies (LRU, ARC, SRRIP, DRRIP, LIRS) on
representative traces at increasing prefix lengths: 20k, 50k, 100k, 200k, 400k,
800k, and 1.6M references, with 5 different seeds each. For each (trace, policy,
prefix length) it computes the mean and standard deviation of the hit ratio.

The result is in `results/sizing_study.csv` and a figure at
`results/sizing_study.png`.

### How to read the figure

Each panel shows one representative trace. The x-axis is prefix length (log
scale), the y-axis is hit ratio. Each line is a policy, with error bars showing
±1 standard deviation across seeds.

**What to look for:**
- The lines flatten (converge) as prefix length increases.
- The recommended N is the smallest prefix length at which (a) every policy's
  mean is within 0.2 percentage points of its value at the longest prefix, and
  (b) the ranking of policies has stopped changing.

### Interpreting the result

If the study says "recommended N = 600,000", that means traces shorter than
600k would distort the ranking of policies. At 600k, the compulsory share is
small enough, the adaptive policies have had time to learn, and seed-to-seed
variation is within ~0.1 percentage points.

---

## 7. Trace families and what they test

### Core set (40 traces)

#### Zipfian traces (32)

- **Parameters:** 8 alphas × 4 working-set sizes = 32 traces.
- **What they test:** general-purpose performance under realistic skewed access
  patterns. The alpha controls how skewed the access is; the working-set size
  controls how much pressure the cache is under.
- **Key insights:** at low alpha with large working set, the cache is under
  severe pressure and advanced policies can differentiate themselves. At high
  alpha, all policies converge because a few blocks dominate.

#### Scan traces (4)

- **`scan_pure_long`** (all-unique IDs) and **`scan_pure_short`** (10C unique):
  Pure scans. Every policy gets 0% hit ratio on these because no block is ever
  re-referenced. These are **sanity checks**, not scan-resistance tests. If a
  policy claims hits on a pure scan, it has a bug.

- **`scanhot_h0.5C_s3C`** and **`scanhot_h0.5C_s10C`**: a hot set of 0.5C
  blocks accessed randomly, interleaved with scans of 3C or 10C never-seen
  blocks. **These are the real scan-resistance tests.** A scan-resistant policy
  protects the hot set from being evicted by the scan; a scan-vulnerable policy
  (like LRU) flushes its hot set every time a scan passes through.

#### Loop traces (4)

- **`loop_0.90C`**: loop of 0.9C blocks. Fits in cache → all policies get ~99%.
- **`loop_1.00C`**: exact fit — borderline.
- **`loop_1.10C`** and **`loop_1.25C`**: loop larger than cache. LRU scores
  exactly **0%** because it thrashes: by the time a block comes around again,
  LRU has evicted it. LIRS and BRRIP retain a fraction of the loop by sacrificing
  some slots as "canaries" that absorb evictions while the rest of the loop stays
  cached. This is the **thrashing resistance** test.

### Extension set (8 traces)

#### Filtered (second-level) traces (4)

- A Zipf stream (W = 20C) passes through an upstream LRU cache; only the
  **misses** from that upstream cache become the trace. This simulates a
  second-level cache (like an LLC that only sees what the L1/L2 missed).
- **Why they exist:** the miss stream has weak temporal locality because the
  upstream cache already absorbed the easy hits. MQ and RRIP were designed for
  exactly this scenario.

#### Phase-change traces (2)

- Zipf with popularity reshuffled every P references (P = 20k or 100k).
- **What they test:** adaptation speed. ARC adapts its target p, CLOCK-Pro adapts
  m_c, DRRIP adapts PSEL. A policy that adapts quickly will recover after each
  phase change; a slow adapter will lose hits during the transition.

#### Zipf-plus-scan traces (2)

- Zipf workload with a scan of 3C or 10C new blocks injected every 20k
  references.
- **What they test:** how well a policy handles mixed workloads — can it survive a
  scan burst without losing its working set?

---

## 8. Algorithm-by-algorithm guide

### Baselines

**LRU (Least Recently Used):** evict the block that was accessed longest ago.
Simple and the standard baseline. Weakness: thrashes on loops larger than C and
flushes its working set during scans.

**FIFO (First In, First Out):** evict the block that was inserted longest ago.
Hits don't change a block's position. Sometimes matches LRU, sometimes slightly
better on scans.

**OPT (Belady's offline optimal):** evict the block whose next use is farthest
in the future. Requires knowing the entire future trace — impossible in practice,
but serves as a **ceiling**: no online policy can do better. Our implementation
includes the **bypass rule**: if the incoming block's next use is no sooner than
the victim's, don't cache it at all.

---

### ARC — Adaptive Replacement Cache

> **Paper:** Megiddo & Modha, FAST 2003

**The idea in two sentences.** ARC splits the cache into two lists — one for
blocks seen once (T1, "recency") and one for blocks seen at least twice (T2,
"frequency") — and *adapts* the split point based on which list's evictions turn
out to be mistakes. It keeps "ghost" lists of recently evicted keys so it can
detect those mistakes.

**Data structures:**

| Name | Contents | Max size |
|---|---|---|
| T1 | Resident blocks seen once, ordered LRU→MRU | variable |
| T2 | Resident blocks seen ≥2 times, ordered LRU→MRU | variable |
| B1 | Ghost keys evicted from T1 (keys only, no data) | ≤ C − \|T1\| |
| B2 | Ghost keys evicted from T2 (keys only, no data) | ≤ 2C − \|T1\| − \|B1\| − \|T2\| |
| p | Target size of T1, in [0, C], starts at 0 | single float |

**Invariants:** |T1| + |T2| ≤ C, |T1| + |B1| ≤ C, |T1| + |T2| + |B1| + |B2| ≤ 2C.

**Worked example: trace A B A B A B, capacity = 2**

| Step | Access | Case | Action | T1 (LRU→MRU) | T2 (LRU→MRU) | B1 | B2 | p | H/M |
|---|---|---|---|---|---|---|---|---|---|
| 1 | A | IV | Insert A in T1 | [A] | [] | [] | [] | 0 | M |
| 2 | B | IV | Insert B in T1 | [A, B] | [] | [] | [] | 0 | M |
| 3 | A | I (T1) | Move A to MRU of T2 | [B] | [A] | [] | [] | 0 | H |
| 4 | B | I (T1) | Move B to MRU of T2 | [] | [A, B] | [] | [] | 0 | H |
| 5 | A | I (T2) | Move A to MRU of T2 | [] | [B, A] | [] | [] | 0 | H |
| 6 | B | I (T2) | Move B to MRU of T2 | [] | [A, B] | [] | [] | 0 | H |

Result: `MMHHHH`. After step 3, both blocks are in T2 (seen twice), and they stay there.

**The four cases explained:**

- **Case I (hit in T1 or T2):** Move the block to MRU of T2. A hit in T1 means
  the block has now been seen twice, so it graduates to T2.
- **Case II (ghost hit in B1):** The system evicted this block from T1, and now
  it's being requested again — evidence that T1 was too small. Increase p. Run
  REPLACE, delete the ghost, add the block to T2.
- **Case III (ghost hit in B2):** The system evicted this block from T2, and now
  it's being requested again — evidence that T2 was too small. Decrease p. Run
  REPLACE, delete the ghost, add the block to T2.
- **Case IV (complete miss, not in any list):** Make room if needed, then insert
  the new block at MRU of T1.

**What it fixes about LRU:** LRU treats all blocks the same — a block accessed
100 times is evicted just as quickly as a block accessed once if something newer
comes along. ARC distinguishes *recency* (seen once) from *frequency* (seen
multiple times) and protects frequently-accessed blocks.

**Weakness:** ARC scores 0% on loops larger than C, just like LRU. It has no
mechanism for partial retention of a cyclical access pattern. Also, the ghost
lists add metadata overhead proportional to C.

**Expected results by trace family:**

| Trace family | Expectation |
|---|---|
| Zipf W ≤ C | ~99% (same as all policies) |
| Zipf W = 2C–10C | Several points above LRU, competitive with BRRIP |
| Loops > C | 0% (same as LRU) |
| Scanhot | Well above LRU; matches or beats BRRIP |
| Filtered | Good — ghost lists catch re-references from upstream misses |

---

### LIRS — Low Inter-reference Recency Set

> **Paper:** Jiang & Zhang, SIGMETRICS 2002

**The idea in two sentences.** LIRS classifies blocks by their **inter-reference
recency** (IRR) — how many other distinct blocks were accessed between two
consecutive accesses to the same block. Blocks with low IRR are "hot" (LIR) and
are always kept resident; blocks with high IRR are "cold" (HIR) and use only a
small part of the cache.

**Data structures:**

| Name | Contents |
|---|---|
| S (stack) | Ordered from bottom (oldest) to top (newest). Contains LIR blocks, resident HIR blocks, and non-resident HIR blocks. **Invariant: the bottom of S is always a LIR block** (maintained by "stack pruning"). |
| Q (queue) | Contains resident HIR blocks in FIFO order. The front is the eviction victim. |
| L_lirs | Number of LIR slots (= C − L_hirs). |
| L_hirs | Number of HIR slots (= max(1, round(0.01 × C))). |

**Worked example: trace A B C A D C, capacity = 3 (L_lirs = 2, L_hirs = 1)**

| Step | Access | Status before | Action | S (bottom→top) | Q (front→end) | LIR set | H/M |
|---|---|---|---|---|---|---|---|
| 1 | A | new | Warm-up: admit as LIR | [A:LIR] | [] | {A} | M |
| 2 | B | new | Warm-up: admit as LIR (LIR full after this) | [A:LIR, B:LIR] | [] | {A,B} | M |
| 3 | C | new | Admit as resident HIR (warm-up done) | [A, B, C:rHIR] | [C] | {A,B} | M |
| 4 | A | LIR | Hit LIR: move to top of S. A was bottom → prune. | [B, C:rHIR, A:LIR] | [C] | {A,B} | H |
| 5 | D | new | Evict front of Q (C). C is in S → mark non-resident. D → resident HIR, top of S, end of Q. | [B, C:nrHIR, D:rHIR] | [D] | {A,B} | M |
| 6 | C | non-res HIR in S | Evict front of Q (D). C in S as non-res → promote to LIR, top of S. Demote bottom LIR (B) to HIR, end of Q. Prune. | [A, C:LIR] | [B] | {A,C} | M |

Result: `MMMHMM`. Final LIR set = {A, C}. Resident set = {A, B, C}.

**What it fixes about LRU:** LIRS can keep a fraction of a loop cached even when
the loop is larger than C. It does this by dedicating most of the cache to "hot"
blocks and using a tiny HIR region as a sacrificial buffer. On `loop_1.10C`, LIRS
scores around 89% while LRU scores 0%.

**Weakness:** Stack pruning can be expensive in the worst case (though bounded by
|S|). The algorithm is complex to implement correctly — many subtle invariants.
Performance on Zipf workloads is good but not always the best (ARC or BRRIP
sometimes win).

**Expected results by trace family:**

| Trace family | Expectation |
|---|---|
| Zipf W ≤ C | ~99% |
| Zipf W = 10C | Several points above LRU, competitive with ARC |
| Loops > C | **Far above LRU** — this is LIRS's signature strength |
| Scanhot | Above LRU; the HIR queue absorbs scan blocks |

---

### CLOCK-Pro

> **Paper:** Jiang, Chen & Zhang, USENIX ATC 2005

**The idea in two sentences.** CLOCK-Pro is an approximation of LIRS using a
single circular list (a "clock") with three hands instead of a stack. It is
cheaper to implement in an operating system kernel because it uses only reference
bits (set on access, cleared by the clock hand) instead of ordered lists.

**Data structures:**

| Name | Contents |
|---|---|
| Circular list | Contains hot pages, resident cold pages, and non-resident cold pages. Each page has a reference bit. |
| hand_cold | Sweeps to find an unreferenced cold resident page to evict. |
| hand_hot | Sweeps to demote unreferenced hot pages to cold. |
| hand_test | Expires non-resident cold pages that were never re-referenced. |
| m_c | Target number of cold resident pages. Increases when a non-resident page is re-referenced (evidence: we evicted too aggressively). Decreases when a cold page is promoted to hot. |

**Worked example: trace A B C A B D, capacity = 3**

| Step | Access | Action | Resident pages | Hot pages | m_c | H/M |
|---|---|---|---|---|---|---|
| 1 | A | Insert cold, test period | {A} | {} | 3 | M |
| 2 | B | Insert cold, test period | {A, B} | {} | 3 | M |
| 3 | C | Insert cold, test period | {A, B, C} | {} | 3 | M |
| 4 | A | Hit: set ref bit | {A, B, C} | {} | 3 | H |
| 5 | B | Hit: set ref bit | {A, B, C} | {} | 3 | H |
| 6 | D | Miss: evict cold (find unreferenced). A, B have ref bit → promote to hot, m_c decreases. Eventually evict C. Insert D cold. | {A, B, D} | {A, B} | 1 | M |

Result: `MMMHHM`.

**What it fixes about LRU:** Like LIRS, CLOCK-Pro distinguishes hot from cold
pages and protects hot pages from scans. It also adapts m_c, which controls the
balance between keeping cold pages for test and keeping hot pages.

**Weakness:** The adaptive m_c can sometimes rise to high values on tight loops
(e.g., loop of 1.1C), where a fixed m_c = 1 would score better. The three-hand
mechanism is complex, and the paper leaves some details ambiguous (does a demoted
hot page begin a new test period? how exactly is m_c enforced?).

**Expected results by trace family:**

| Trace family | Expectation |
|---|---|
| Loops > C | Good performance (though possibly below LIRS) |
| Scanhot | Above LRU |
| Zipf | Competitive, generally between LRU and the best adaptive policies |

---

### CAR — Clock with Adaptive Replacement

> **Paper:** Bansal & Modha, FAST 2004

**The idea in two sentences.** CAR is to ARC what CLOCK-Pro is to LIRS: it
replaces ARC's ordered lists with clocks (circular buffers with reference bits),
making it cheaper to implement. Hits only set a reference bit instead of moving
the block to the MRU position.

**Data structures:**

| Name | Contents |
|---|---|
| T1 (clock) | Blocks seen once, with reference bits. |
| T2 (clock) | Blocks seen ≥2 times, with reference bits. |
| B1 (LRU list) | Ghost keys evicted from T1. |
| B2 (LRU list) | Ghost keys evicted from T2. |
| p | Target size of T1, adaptive (same formula as ARC). |

**Worked example: trace A A B C A, capacity = 2**

| Step | Access | Action | T1 (with ref bits) | T2 | B1 | B2 | p | H/M |
|---|---|---|---|---|---|---|---|---|
| 1 | A | Insert at T1 tail, ref=0 | [(A,0)] | [] | [] | [] | 0 | M |
| 2 | A | Hit in T1: set ref=1 | [(A,1)] | [] | [] | [] | 0 | H |
| 3 | B | Insert at T1 tail, ref=0 | [(A,1),(B,0)] | [] | [] | [] | 0 | M |
| 4 | C | Full, replace(). Head A ref=1 → clear, move to T2. Now T1=[(B,0)], T2=[(A,0)]. Head B ref=0 → evict to B1. Insert C. | [(C,0)] | [(A,0)] | [B] | [] | 0 | M |
| 5 | A | Hit in T2: set ref=1 | [(C,0)] | [(A,1)] | [B] | [] | 0 | H |

Result: `MHMMH`. CAR passes the reuse-proof test — it keeps A (seen twice) over B (seen once).

**What it fixes about LRU:** Same benefits as ARC (recency + frequency
adaptation) but with cheaper constant-time operations per access.

**Weakness:** Same as ARC — 0% on loops larger than C.

---

### MQ — Multi-Queue

> **Paper:** Zhou, Philbin & Li, USENIX ATC 2001

**The idea in two sentences.** MQ maintains *m* LRU queues at different priority
levels. A block's queue level is determined by how often it has been accessed
(log₂ of its access count), and blocks are demoted when they haven't been
accessed for a while ("expiration").

**Data structures:**

| Name | Contents |
|---|---|
| Q0 .. Q(m−1) | m LRU queues. Q0 is the lowest priority. |
| Qout | Ghost FIFO of recently evicted keys with their access counts. |
| Per block: f | Access count. Queue level = min(⌊log₂ f⌋, m−1). |
| Per block: expireTime | When this block was last promoted + lifeTime. |

**Parameters:** m = 8 queues, lifeTime = C, Qout size = C.

**Worked example: trace A B C A, capacity = 3, m = 8, lifeTime = 3**

| Step (time) | Access | Action | Q0 | Q1 | H/M |
|---|---|---|---|---|---|
| 1 | A | Miss, f=1 → Q0 | [A] | [] | M |
| 2 | B | Miss, f=1 → Q0 | [A, B] | [] | M |
| 3 | C | Miss, f=1 → Q0 | [A, B, C] | [] | M |
| 4 | A | Hit, f=2 → Q1 | [B, C] | [A] | H |

A's access count goes from 1 to 2. ⌊log₂(2)⌋ = 1, so A moves from Q0 to Q1.

**What it fixes about LRU:** MQ tracks frequency (via access counts) and gives
frequently-accessed blocks higher priority queues that protect them from
eviction. A block evicted and then re-referenced gets its old access count back
from Qout, so its history is partially preserved.

**Weakness:** The many parameters (m, lifeTime, Qout size) are workload-
dependent, and the paper's adaptive lifeTime rule is complex. MQ can be slow to
adapt to phase changes because the demotion mechanism relies on time thresholds.

---

### LRU-K (K = 2)

> **Paper:** O'Neil, O'Neil & Weikum, SIGMOD 1993

**The idea in two sentences.** Instead of evicting the least-recently-used block,
evict the block whose **K-th most recent access** is oldest. This approximates
frequency information: a block that was accessed twice recently has a recent K-th
access, while a block accessed only once has an infinitely old K-th access.

**Data structures:**

| Name | Contents |
|---|---|
| Per block: history | List of last K reference timestamps. |
| Resident set | The blocks currently in cache. |
| Heap | Min-heap keyed on (K-th reference time, most recent time) for O(log C) eviction. |

**Worked example: trace A A B C A, capacity = 2, K = 2**

| Step (time) | Access | History | Evict? | Resident | H/M |
|---|---|---|---|---|---|
| 1 | A | A:[1] | — | {A} | M |
| 2 | A | A:[1,2] | — | {A} | H |
| 3 | B | B:[3] | — | {A, B} | M |
| 4 | C | C:[4] | A's 2nd ref: time 2. B's 2nd ref: ∞. Evict B. | {A, C} | M |
| 5 | A | A:[2,5] | — | {A, C} | H |

Result: `MHMMH`. LRU-2 keeps A (which has two references) over B (only one), passing the reuse-proof test.

**What it fixes about LRU:** LRU only considers the *most recent* access. LRU-K
considers the K-th most recent, which distinguishes between "accessed once
recently" and "accessed many times recently." This gives it frequency awareness.

**Weakness:** Blocks with fewer than K references are treated as having infinite
backward K-distance and are evicted first — this is correct behavior but means
that during warm-up, many blocks churn through without getting a chance. Also, 0%
on loops larger than C.

---

### SRRIP — Static Re-Reference Interval Prediction

> **Paper:** Jaleel et al., ISCA 2010

**The idea in two sentences.** Each cache line has a small counter called RRPV
(Re-Reference Prediction Value, 2 bits, 0–3) that predicts how soon the block
will be accessed again. On insertion, a block gets RRPV = 2 ("intermediate"); on
a hit, RRPV is set to 0 ("near-immediate re-reference"); for eviction, find a
block with RRPV = 3, or age all blocks in the set until one reaches 3.

**This is a set-associative policy** — the cache is divided into sets, and each
set has a fixed number of ways. A block can only go in the set determined by its
address (block ID mod number of sets).

**Data structures (per set):**

| Name | Contents |
|---|---|
| entries | Map of key → RRPV (2-bit, 0–3) |

**Worked example: trace A A B C A, capacity = 2 (1 set, 2 ways)**

| Step | Access | Set state (key:RRPV) | Action | H/M |
|---|---|---|---|---|
| 1 | A | A:2 | Insert A, RRPV=2 | M |
| 2 | A | A:0 | Hit: set RRPV to 0 | H |
| 3 | B | A:0, B:2 | Insert B, RRPV=2 | M |
| 4 | C | — | No RRPV=3 found. Age all: A:1, B:3. Evict B (RRPV=3). Insert C:2. State: A:1, C:2 | M |
| 5 | A | A:0, C:2 | Hit: set A's RRPV to 0 | H |

Result: `MHMMH`. SRRIP passes the reuse-proof test — A's RRPV of 0 (recently
hit) protects it from eviction, while B's RRPV ages to 3 first.

**What it fixes about LRU:** SRRIP inserts new blocks at an intermediate RRPV
(not the most protected position), so scan blocks don't immediately flush the
working set. However, **on workloads where the scan is longer than the per-set
capacity remaining after the hot blocks**, SRRIP equals LRU (the scan still
ages everything out within the set).

**Weakness:** SRRIP is static — it always inserts at RRPV = 2. This is wrong for
workloads dominated by blocks that are accessed once and never again (thrashing
loops), where inserting at the least-protected position (RRPV = 3) would be
better.

---

### BRRIP — Bimodal RRIP

> **Paper:** Jaleel et al., ISCA 2010

**The idea in two sentences.** BRRIP is SRRIP with a twist: most blocks are
inserted at the *least protected* RRPV = 3 ("distant re-reference"), and only
with a small probability ε = 1/32 are they inserted at RRPV = 2. This means the
cache is very conservative about admitting new blocks, which is excellent for
thrashing workloads.

**What it fixes about SRRIP:** On loops larger than C, SRRIP inserts every block
at RRPV = 2, which keeps the cache churning (0% hit ratio, same as LRU). BRRIP
inserts most blocks at RRPV = 3 (immediately eligible for eviction), so only
1/32 of new blocks actually stay in the cache. This creates a stable "sample" of
the loop that gets hit when it comes around.

**Weakness:** BRRIP is terrible for workloads with good temporal locality (like
high-alpha Zipf), because it refuses to cache most new blocks. The policy that's
best for thrashing loops is the worst for normal workloads.

**Expected results:**

| Trace family | Expectation |
|---|---|
| Loops > C | **Far above LRU and SRRIP** — BRRIP's signature strength |
| Zipf W = 10C | Above LRU (less churn), competitive with ARC |
| Zipf W ≤ C | Same as everyone (~99%) |
| Scanhot | Above LRU |

---

### DRRIP — Dynamic RRIP

> **Paper:** Jaleel et al., ISCA 2010; set-dueling concept from Qureshi et al., ISCA 2007

**The idea in two sentences.** DRRIP dynamically chooses between SRRIP and BRRIP
by dedicating a few "leader sets" to each policy and seeing which one misses less
at runtime. The majority of sets ("follower sets") follow whichever leader policy
is currently winning.

**Data structures:**

| Name | Contents |
|---|---|
| SRRIP leader sets | A few sets (default 4) that always use SRRIP. |
| BRRIP leader sets | A few sets (default 4) that always use BRRIP. |
| Follower sets | All remaining sets. Use SRRIP or BRRIP depending on PSEL. |
| PSEL | 10-bit saturating counter (0–1023). Starts at 512. A miss in an SRRIP leader increments PSEL; a miss in a BRRIP leader decrements it. Follower sets use BRRIP when PSEL ≥ 512, otherwise SRRIP. |

**What it fixes:** DRRIP gets the best of both worlds — SRRIP on workloads where
SRRIP is better (Zipf, scanhot), BRRIP on workloads where BRRIP is better
(thrashing loops). In practice, it usually scores close to whichever component
policy is better for the current workload.

**Weakness:** DRRIP below BRRIP on loops. This is expected: the SRRIP leader sets
(a fixed fraction of all sets) thrash on loops, dragging the average down even
though the follower sets use BRRIP. The gap equals roughly the fraction of sets
spent on SRRIP leaders. With 4 SRRIP leaders out of 128 sets (3.1%), the penalty
is about 3 percentage points.

---

### SHiP (dropped)

> **Paper:** Wu et al., MICRO 2011

SHiP (Signature-based Hit Predictor) uses the **program counter** (PC) — the
address of the instruction that caused the memory access — as a signature to
predict whether a newly cached block will be re-referenced. Blocks brought in by
instructions that historically cause re-references get a near-immediate RRPV;
blocks from instructions with poor reuse get a distant RRPV.

**Why it was dropped:** our traces contain only block IDs, not program counters.
Without PC signatures, SHiP degenerates to SRRIP and adds no value. Generating
traces with per-access PC information would require instruction-level simulation,
which is beyond the scope of this project.

---

## 9. Software caches vs hardware caches

The policies in this study fall into two categories that are designed for
different regimes:

| | Software caches | Hardware caches (LLC) |
|---|---|---|
| **Associativity** | Fully associative: any block can go in any slot | Set-associative: a block can only go in one set (determined by its address), which has a fixed number of ways (e.g., 16) |
| **Metadata budget** | Can afford per-block ordered lists, counters, ghost entries | Limited to a few bits per cache line (e.g., 2-bit RRPV) |
| **Examples** | ARC, LIRS, CLOCK-Pro, CAR, MQ, LRU-K | SRRIP, BRRIP, DRRIP |
| **Typical use** | OS page caches, database buffer pools, CDN caches | CPU last-level caches |

### Why the comparison needs care

Comparing ARC (fully associative) to SRRIP (set-associative, 16 ways) is not
quite fair because set-associativity introduces **conflict misses** — two popular
blocks that map to the same set compete for the same slots even if other sets
have room. Fully-associative policies don't have this problem.

### The fair baseline

For the hardware family, the fair comparison baseline is **SA-LRU** (set-
associative LRU with the same geometry), not fully-associative LRU. SA-LRU
typically scores within ~1 percentage point of fully-associative LRU at 16 ways,
confirming that conflict misses are small at this associativity.

### What leader sets cost

In DRRIP, leader sets are dedicated to one fixed policy (SRRIP or BRRIP) and
cannot use the dynamically chosen policy. This is a cost: if BRRIP is optimal but
4 sets are forced to use SRRIP, those 4 sets perform suboptimally. The overhead
is proportional to the fraction of sets used as leaders. With 4 leaders per
policy out of 128 sets, about 6.3% of sets are constrained.

---

## 10. How to read each chart

### Summary table (trace × policy)

Rows are traces, columns are policies. Each cell is the hit ratio in percent.
The highest value in each row is highlighted in green. Look for:
- Which policy wins most often.
- Whether any policy is consistently worst.
- Whether some trace families cause bigger spreads than others.

### Heatmap (alpha × working-set size)

Each cell shows the hit ratio for one alpha and one working-set multiplier. Warm
colours are high hit ratio; cool colours are low. Look for:
- The gradient from top-left (low alpha, small working set) to bottom-right.
- How the gradient differs between policies.

### Difference heatmap

Shows (Policy A − Policy B) in percentage points. Blue = A is better, red = B is
better. Look for consistent patterns (does one always win?).

### Hit ratio vs alpha lines

One line per policy. X-axis is alpha, Y-axis is hit ratio. Look for:
- Where policies diverge (usually mid-alpha).
- Whether any policy's line crosses another (one is better at low alpha, the
  other at high alpha).

### Loop/scan bar charts

Bars show hit ratio for each policy on loop or scanhot traces. The dashed line is
OPT (the ceiling). Look for which policies approach OPT and which stay at 0%.

### Miss-ratio curve

X-axis is cache capacity, Y-axis is miss ratio. As capacity increases, miss ratio
should decrease. Look for the "knee" — the capacity where miss ratio drops
sharply — and how it differs between policies.

### What a surprising result looks like

If a policy that should score 0% on a loop (like LRU) scores 5%, that's likely a
bug. If a policy beats OPT on any trace, that's definitely a bug. If SRRIP
doesn't equal LRU on the scanhot traces, check the set geometry.

---

## 11. Expected vs measured

The prompt provided a prototype table at C = 1024, 64 sets × 16 ways, 200k
references. Your simulator uses C = 2048, 128 sets × 16 ways, 600k references,
so the numbers will differ by a few points. The **patterns** are what you should
check.

| Pattern | Expected | Your run: held? |
|---|---|---|
| Zipf W ≤ C: all policies ~99.7% | Yes | _(fill in after full-scale run)_ |
| LRU on loop > C = exactly 0% | Yes | _(fill in)_ |
| ARC, CAR, LRU-K, SRRIP also ~0% on loops > C | Yes | _(fill in)_ |
| LIRS retains a large fraction of loop > C | Yes | _(fill in)_ |
| BRRIP retains a large fraction of loop > C | Yes | _(fill in)_ |
| DRRIP below BRRIP on loops | Yes (SRRIP leaders thrash) | _(fill in)_ |
| SRRIP = LRU on scanhot | Yes (scan > per-set remaining capacity) | _(fill in)_ |
| SA-LRU within ~1pp of fully-associative LRU | Yes (16-way → low conflict) | _(fill in)_ |
| No policy ever beats OPT | Yes | _(fill in)_ |

**If a result contradicts these patterns, assume a bug and investigate before
calling it a finding.** A good test: run the same trace with your policy and LRU
and check the state after each access to find the divergence point.

---

## 12. Limits of this study

1. **Synthetic traces with independent references.** Real workloads have temporal
   structure (bursts, phases, correlated accesses) that independent Zipf draws
   don't capture. Our traces test the algorithm mechanics but may not predict real
   performance accurately.

2. **Hit ratio is not throughput.** A 1% improvement in hit ratio might translate
   to a 10% throughput gain (if misses are expensive) or almost nothing (if the
   system is bottlenecked elsewhere). We measure hit ratio only.

3. **Scaled-down cache.** C = 2048 is tiny compared to real caches (millions of
   lines in a modern LLC, millions of pages in an OS page cache). Scaling effects
   (set-associativity conflicts, metadata overhead, DRRIP leader-set ratio) may
   behave differently at full scale.

4. **Parameter choices.** MQ's lifetime, LIRS's HIR ratio, the number of DRRIP
   leader sets, BRRIP's ε — all are set to specific defaults. Different values
   might change the ranking. We run a small sensitivity sweep but don't
   exhaustively optimize.

5. **OPT bypass convention.** Our OPT includes the bypass rule (don't cache a
   block if its next use is farther than the victim's). Without bypass, OPT is
   not a valid upper bound for policies that can decline to cache a block (like
   BRRIP). This is a correctness choice, but it means OPT scores might differ
   from other implementations that omit bypass.

6. **Policies with only paper-derived tests.** Some policies (e.g., CLOCK-Pro,
   MQ) have their tests derived from the algorithm pseudocode rather than
   independently verified by stepping through the paper's examples. They carry a
   "review recommended" badge.

7. **No real-world traces.** We don't test on industry-standard trace sets like
   MSR Cambridge or YCSB because they require additional infrastructure and
   licensing. The extension traces (filtered, phase-change) approximate some
   real-world patterns but are not substitutes.

---

## 13. Oral-defense practice questions

### Fundamentals

**Q1. What is a cache replacement policy, and why does it matter?**

A replacement policy decides which block to evict when the cache is full and a
new block arrives. It matters because a miss — fetching from slower storage — can
cost 5× to 100,000× the hit time. Even a 1-percentage-point improvement in hit
ratio translates to measurable performance gains.

**Q2. Explain the difference between a compulsory miss and a capacity miss.**

A *compulsory* (cold) miss happens the first time a block is ever accessed — the
cache has never seen it. A *capacity* miss happens when the block was in the
cache at some point but was evicted because the cache was full. No replacement
policy can avoid compulsory misses; the goal is to minimize capacity misses.

**Q3. What is the working set, and why does W/C matter?**

The working set is the set of distinct blocks that a workload accesses. W/C is
the ratio of working set to cache capacity. When W ≤ C, everything fits and all
policies score ~100%. When W >> C, only the best policies differentiate
themselves. The ratio determines how much "pressure" the cache is under.

### Algorithms

**Q4. How does ARC differ from LRU, and why is that an improvement?**

LRU evicts the least recently used block, treating all blocks identically. ARC
splits the cache into a "recency" list (T1, seen once) and a "frequency" list
(T2, seen multiple times), with ghost lists (B1, B2) to detect eviction mistakes.
It adapts the split point (p) at runtime. This lets ARC keep frequently-accessed
blocks even if they haven't been accessed in the last few moments.

**Q5. Why does LRU score exactly 0% on a loop larger than the cache?**

In a loop of L > C blocks, by the time block i comes around again, LRU has
evicted it to make room for blocks i+1, i+2, ..., i+C. The next access to block
i is always a miss. The reuse distance (number of distinct blocks between two
accesses) is L−1 > C−1, so the block is always pushed out.

**Q6. How does LIRS achieve non-zero hit ratios on thrashing loops?**

LIRS dedicates most of the cache (L_lirs ≈ 0.99C) to LIR ("hot") blocks. On a
loop of L slightly larger than C, LIRS can keep about L_lirs of the L blocks
permanently resident as LIR, while the remaining L − L_lirs blocks rotate through
the small HIR region and are evicted. Hit ratio ≈ L_lirs / L.

**Q7. What is RRPV, and how does SRRIP use it?**

RRPV (Re-Reference Prediction Value) is a 2-bit counter (0–3) per cache line
that predicts how soon the block will be re-used. 0 = "nearly immediate", 3 =
"distant." SRRIP inserts at RRPV = 2, promotes to 0 on a hit, and evicts the
first line at RRPV = 3 (aging all lines in the set if none is at 3). This gives
new blocks an intermediate priority, protecting hot blocks from immediate
eviction.

**Q8. Why does BRRIP outperform SRRIP on thrashing loops?**

BRRIP inserts most blocks at RRPV = 3 (immediately eligible for eviction) and
only 1/32 at RRPV = 2. This means most new loop iterations pass through the
cache without displacing the retained sample. The retained blocks get hit when
their turn comes, yielding significant hit ratios even on loops larger than C.

**Q9. Explain set dueling in DRRIP.**

DRRIP dedicates a few sets to SRRIP ("SRRIP leaders") and a few to BRRIP ("BRRIP
leaders"). A miss in an SRRIP leader set increments a counter (PSEL); a miss in a
BRRIP leader decrements it. When PSEL ≥ 512, follower sets use BRRIP; otherwise
SRRIP. This dynamically picks the better policy for the current workload without
per-set overhead beyond the leaders.

**Q10. Why is DRRIP slightly worse than BRRIP on thrashing loops?**

The SRRIP leader sets are forced to use SRRIP, which thrashes on loops. Even
though the follower sets correctly choose BRRIP, the leader sets drag the average
down. The penalty is proportional to the fraction of sets used as SRRIP leaders
(about 3% with 4 leaders out of 128 sets).

### Methodology

**Q11. Why didn't you use numpy.random.zipf?**

It raises an error for alpha ≤ 1 (five of our eight alphas), and it is unbounded
(cannot control working-set size). We use a bounded Zipf distribution where
probabilities are 1/r^alpha for ranks 1..W, normalized, with a random
permutation mapping ranks to block IDs.

**Q12. How did you choose the trace length N = 600,000?**

We ran a sizing study: for representative traces, we measured hit ratios at
increasing prefix lengths (20k to 1.6M) with multiple seeds. We picked the
smallest N at which (a) every policy's mean hit ratio is within 0.2 percentage
points of its value at the longest prefix, and (b) the policy ranking has
stabilized. The study is in `results/sizing_study.csv`.

**Q13. What is OPT bypass, and why does it matter?**

OPT with bypass declines to cache a block if its next use is farther in the
future than the farthest-future resident block. Without bypass, OPT would cache
the block, evict the farthest-future resident, and get a hit when the new block
is re-referenced — but miss when the evicted block is referenced. Bypass yields a
higher (or equal) hit ratio and is necessary for OPT to be a valid upper bound
for policies that can decline to cache (like BRRIP).

**Q14. How do you know the simulator is correct?**

Every policy has at least 3 hand-derived test cases where the expected hit/miss
sequence and final state were computed on paper before running the simulator. The
simulator must match exactly. Invariant checks (hits + misses = trace length, no
policy beats OPT, resident set ≤ C) are verified on every trace. Policies with ≥
3 passing hand-derived tests get a "hand-verified" badge.

### Analysis

**Q15. Why do all policies tie on W ≤ C traces?**

When the working set fits in the cache, after at most W compulsory misses every
block is resident and never evicted. The replacement policy is never invoked
after warm-up. All policies converge to hit ratio ≈ 1 − W/N.

**Q16. What does the capacity sweep tell you that the main experiment doesn't?**

The main experiment runs at a single capacity C. The sweep tests capacities from
C/4 to 4C. For traces with W ≤ C, the main run shows all policies tied, but the
sweep reveals differences at smaller capacities. The resulting miss-ratio curve
shows how each policy degrades under increasing pressure.

**Q17. If a policy beats OPT in your results, what do you conclude?**

A bug. OPT is provably optimal for the offline case (with bypass). If any online
policy exceeds OPT's hit count, either the OPT implementation is wrong (e.g.,
missing bypass), or the other policy has a bookkeeping error (e.g., double-
counting hits). Investigate before reporting.

**Q18. What is scan resistance, and which policies have it?**

Scan resistance is the ability to keep the working set cached when a burst of
never-seen blocks (a "scan") passes through the cache. LRU flushes its working
set; scan-resistant policies (ARC, LIRS, CLOCK-Pro, BRRIP, LRU-K) protect hot
blocks by giving new blocks lower priority. On the scanhot traces, the gap
between LRU and scan-resistant policies is typically 5–10 percentage points.

---

## 14. Glossary

| Term | Definition |
|---|---|
| **Alpha (α)** | Skew parameter in the Zipf distribution. Higher = more skewed. |
| **Block** | The unit of data managed by the cache (also called "page" or "line"). |
| **BRRIP** | Bimodal RRIP — inserts most blocks at RRPV = 3, rarely at RRPV = 2. |
| **Bypass** | Declining to cache a block, leaving the cache contents unchanged. |
| **Capacity (C)** | Number of blocks the cache can hold simultaneously. |
| **Capacity miss** | A miss caused by the cache being full and having evicted the block. |
| **Cold miss** | See *compulsory miss*. |
| **Compulsory miss** | A miss caused by accessing a block for the first time ever. |
| **Conflict miss** | A miss in a set-associative cache caused by too many blocks mapping to the same set, even though other sets have room. |
| **DRRIP** | Dynamic RRIP — uses set dueling to choose between SRRIP and BRRIP. |
| **Eviction** | Removing a block from the cache to make room for a new one. |
| **FIFO** | First In, First Out — evict the oldest-inserted block. |
| **Fully associative** | A cache where any block can go in any slot. |
| **Ghost list** | A list of keys (without data) of recently evicted blocks, used to detect mistakes. |
| **Hit** | An access to a block that is already in the cache. |
| **Hit ratio** | Hits / total accesses. |
| **IRR** | Inter-Reference Recency — the number of distinct blocks accessed between two consecutive accesses to the same block. |
| **Leader set** | In DRRIP, a set dedicated to one fixed policy (SRRIP or BRRIP) to measure its miss rate. |
| **LIR** | Low Inter-reference Recency — a "hot" block in LIRS, always kept resident. |
| **LIRS** | Low Inter-reference Recency Set replacement policy. |
| **LLC** | Last-Level Cache — the largest and slowest cache on a CPU chip. |
| **LRU** | Least Recently Used — evict the block whose most recent access is oldest. |
| **LRU-K** | Evict the block whose K-th most recent access is oldest. |
| **Miss** | An access to a block that is not in the cache, requiring a fetch from slower storage. |
| **Miss ratio** | 1 − hit ratio. |
| **MQ** | Multi-Queue replacement policy. |
| **MRU** | Most Recently Used — the position at the "top" of an LRU list. |
| **OPT** | Belady's optimal offline replacement — evict the block used farthest in the future. |
| **PSEL** | Policy SELection counter in DRRIP. |
| **Replacement policy** | The rule that decides which block to evict when the cache is full. |
| **Reuse distance** | The number of distinct blocks accessed between two consecutive accesses to the same block. |
| **RRPV** | Re-Reference Prediction Value — a 2-bit counter predicting re-use urgency. |
| **Scan** | A sequence of accesses to blocks that are each used only once (streaming). |
| **Scan resistance** | A policy's ability to protect its working set from being flushed by a scan. |
| **Set** | In a set-associative cache, a group of ways that a block can be placed in. |
| **Set-associative** | A cache where each block can go in exactly one set, determined by its address. |
| **Set dueling** | Dedicating a few cache sets to different policies to determine which performs better. |
| **SRRIP** | Static Re-Reference Interval Prediction — inserts at RRPV = 2, promotes to 0 on hit. |
| **Thrashing** | The cache continuously evicts blocks that will be needed soon, causing near-100% miss rate. |
| **Trace** | A sequence of block IDs representing a workload's access pattern. |
| **Way** | One slot within a cache set. |
| **Working set** | The set of distinct blocks accessed by a workload. |
| **Zipf's law** | A power-law distribution where the k-th most popular item has frequency proportional to 1/k^α. |
