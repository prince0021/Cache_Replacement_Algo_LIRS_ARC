# Manual Tracing Guide

This guide teaches you how to hand-trace ARC and LIRS on paper — the two algorithms your professor is most likely to ask about in an oral defense. The worksheets at the end give you practice.

---

## Part 1: How to hand-trace ARC

### Data structures

ARC maintains four ordered lists and one number:

| Name | What it holds | Meaning |
|------|--------------|---------|
| **T1** | Resident pages seen **once** recently | "Recency" list |
| **T2** | Resident pages seen **at least twice** recently | "Frequency" list |
| **B1** | Ghost entries evicted from T1 (keys only, no data) | Remembers recent one-timers |
| **B2** | Ghost entries evicted from T2 (keys only, no data) | Remembers recent repeaters |
| **p** | A number between 0 and C (starts at 0) | Target size of T1 — higher p = more room for recency |

**Invariant:** |T1| + |T2| ≤ C (never more than C resident pages).

### Notation

Write lists from LRU (left) to MRU (right). Example: `T1=[B,C]` means B is the LRU end (evicted first) and C is the MRU end.

### The four cases

On each access to page **x**:

| Case | Condition | What happens |
|------|-----------|-------------|
| **I** (hit) | x in T1 or T2 | Move x to MRU of T2. |
| **II** (ghost hit B1) | x in B1 | Increase p. Call REPLACE(x, p). Delete x from B1. Insert x at MRU of T2. |
| **III** (ghost hit B2) | x in B2 | Decrease p. Call REPLACE(x, p). Delete x from B2. Insert x at MRU of T2. |
| **IV** (full miss) | x is nowhere | Manage ghost/resident limits (see below). Insert x at MRU of T1. |

### REPLACE(x, p)

Decides whether to evict from T1 or T2:

- If T1 is non-empty **AND** ( |T1| > p **OR** (x ∈ B2 **AND** |T1| = p) ):
  → evict LRU of T1 → move that key to MRU of B1
- Otherwise:
  → evict LRU of T2 → move that key to MRU of B2

**Key point:** REPLACE runs while x is **still in its ghost list** (don't delete x first).

### Adaptation formulas

- **Case II** (B1 hit): δ = max(1, |B2|/|B1|). Then p ← min(p + δ, C).
- **Case III** (B2 hit): δ = max(1, |B1|/|B2|). Then p ← max(p − δ, 0).

### Case IV details (before inserting x into T1)

- If |T1| + |B1| = C:
  - If |T1| < C: delete LRU of B1, then call REPLACE.
  - Else (|T1| = C): delete LRU of T1 with **no ghost** (doesn't go to B1).
- Else if |T1| + |B1| < C and total ≥ C:
  - If total = 2C: delete LRU of B2.
  - Call REPLACE.

(total = |T1| + |T2| + |B1| + |B2|)

### What to write after each step

| Column | Content |
|--------|---------|
| Step # | 1, 2, 3, … |
| Access | The page being accessed |
| Case | I, II, III, or IV |
| H/M | H for Case I, M for Cases II/III/IV |
| p (after) | Value of p after adaptation |
| T1, T2, B1, B2 | Lists from LRU→MRU |

### Common mistakes

1. **Running REPLACE after deleting the ghost.** REPLACE must see x still in B1 or B2.
2. **Case IV when |T1| = C.** The victim leaves the system entirely — no ghost.
3. **Direction of p.** Case II (B1 hit) → p goes **up**. Case III (B2 hit) → p goes **down**.
4. **Forgetting to move x to MRU of T2** on a T2 hit (Case I).

---

## Part 2: How to hand-trace LIRS

### Data structures

| Name | Contents |
|------|----------|
| **S** (stack) | Bottom to top. Holds LIR blocks, resident HIR blocks, non-resident HIR blocks. **Bottom is always LIR** (maintained by pruning). |
| **Q** (queue) | Front to end. Holds only **resident HIR** blocks. Front = next eviction victim. |

Each block has a **status**: LIR, resident HIR (res_hir), or non-resident HIR (nonres_hir).

### Parameters

- **L_lirs** = C − L_hirs
- **L_hirs** = max(1, round(0.01 × C))

For C=3: L_hirs=1, L_lirs=2. For C=4: L_hirs=1, L_lirs=3.

### Algorithm summary

**Warm-up:** Until n_lir = L_lirs, every new miss enters as LIR directly.

After warm-up:

| Event | Action |
|-------|--------|
| **Hit on LIR x** | Move x to top of S. If x was bottom → prune. |
| **Hit on resident HIR x, x in S** | Promote x to LIR (top of S). Remove from Q. Demote bottom-of-S LIR to resident HIR (end of Q, remove from S). Prune. |
| **Hit on resident HIR x, x not in S** | Move x to top of S and end of Q (stays HIR). |
| **Miss** | If cache full: evict front of Q (if in S → mark non-resident, else forget). Then: |
| — x in S as non-resident | Promote to LIR (top of S). Demote bottom LIR to res HIR. Prune. |
| — x is brand new | Admit as res HIR: top of S + end of Q. |

### Stack pruning

After the bottom of S may have changed, keep removing bottom entries until the bottom is LIR. Non-resident entries removed by pruning are forgotten completely.

### Notation

`S=[A(L), B(L), C(H)]` — bottom to top, (L)=LIR, (H)=resident HIR, (N)=non-resident HIR.
`Q=[C]` — front to end.

### Common mistakes

1. **Forgetting to prune** after the bottom of S changes.
2. **Not keeping evicted blocks in S.** When you evict from Q, if that block is in S, it stays as non-resident HIR.
3. **Thinking non-resident promotion is a hit.** It's still a miss (the data wasn't cached).
4. **Warm-up count.** Ends at exactly L_lirs LIR blocks, not when the cache is full.

---

## Worksheets

Answers are in `ANSWER_KEY.md`. Attempt these first!

---

### Worksheet 1 — ARC: Cases I and IV (warm-up)

**Capacity:** 3
**Trace:** A B C A B D A (7 references)

| Step | Access | Case | H/M | p | T1 (LRU→MRU) | T2 (LRU→MRU) | B1 (LRU→MRU) | B2 (LRU→MRU) |
|------|--------|------|-----|---|---------------|---------------|---------------|---------------|
| 1 | A | | | | | | | |
| 2 | B | | | | | | | |
| 3 | C | | | | | | | |
| 4 | A | | | | | | | |
| 5 | B | | | | | | | |
| 6 | D | | | | | | | |
| 7 | A | | | | | | | |

**H/M string:** __ __ __ __ __ __ __

---

### Worksheet 2 — ARC: Case II (B1 ghost hits, p rises)

**Capacity:** 3
**Trace:** A B A C D B C (7 references)

| Step | Access | Case | H/M | p | T1 (LRU→MRU) | T2 (LRU→MRU) | B1 (LRU→MRU) | B2 (LRU→MRU) |
|------|--------|------|-----|---|---------------|---------------|---------------|---------------|
| 1 | A | | | | | | | |
| 2 | B | | | | | | | |
| 3 | A | | | | | | | |
| 4 | C | | | | | | | |
| 5 | D | | | | | | | |
| 6 | B | | | | | | | |
| 7 | C | | | | | | | |

**H/M string:** __ __ __ __ __ __ __

---

### Worksheet 3 — ARC: Case III (B2 ghost hit, p falls)

**Capacity:** 3
**Trace:** A B A C D B E A (8 references)

| Step | Access | Case | H/M | p | T1 (LRU→MRU) | T2 (LRU→MRU) | B1 (LRU→MRU) | B2 (LRU→MRU) |
|------|--------|------|-----|---|---------------|---------------|---------------|---------------|
| 1 | A | | | | | | | |
| 2 | B | | | | | | | |
| 3 | A | | | | | | | |
| 4 | C | | | | | | | |
| 5 | D | | | | | | | |
| 6 | B | | | | | | | |
| 7 | E | | | | | | | |
| 8 | A | | | | | | | |

**H/M string:** __ __ __ __ __ __ __ __

---

### Worksheet 4 — LIRS: Warm-up, LIR hit, pruning

**Capacity:** 3 (L_lirs=2, L_hirs=1)
**Trace:** A B C A D B (6 references)

| Step | Access | Event | H/M | S (bottom→top, with status) | Q (front→end) | n_lir | Prune? |
|------|--------|-------|-----|-----------------------------|----------------|-------|--------|
| 1 | A | | | | | | |
| 2 | B | | | | | | |
| 3 | C | | | | | | |
| 4 | A | | | | | | |
| 5 | D | | | | | | |
| 6 | B | | | | | | |

**H/M string:** __ __ __ __ __ __

---

### Worksheet 5 — LIRS: HIR-in-S promotion, LIR demotion

**Capacity:** 3 (L_lirs=2, L_hirs=1)
**Trace:** A B C A C E C (7 references)

| Step | Access | Event | H/M | S (bottom→top, with status) | Q (front→end) | n_lir | Prune? |
|------|--------|-------|-----|-----------------------------|----------------|-------|--------|
| 1 | A | | | | | | |
| 2 | B | | | | | | |
| 3 | C | | | | | | |
| 4 | A | | | | | | |
| 5 | C | | | | | | |
| 6 | E | | | | | | |
| 7 | C | | | | | | |

**H/M string:** __ __ __ __ __ __ __

---

### Worksheet 6 — LIRS: Non-resident HIR promotion

**Capacity:** 4 (L_lirs=3, L_hirs=1)
**Trace:** A B C D E C D F D (9 references)

| Step | Access | Event | H/M | S (bottom→top, with status) | Q (front→end) | n_lir | Prune? |
|------|--------|-------|-----|-----------------------------|----------------|-------|--------|
| 1 | A | | | | | | |
| 2 | B | | | | | | |
| 3 | C | | | | | | |
| 4 | D | | | | | | |
| 5 | E | | | | | | |
| 6 | C | | | | | | |
| 7 | D | | | | | | |
| 8 | F | | | | | | |
| 9 | D | | | | | | |

**H/M string:** __ __ __ __ __ __ __ __ __
