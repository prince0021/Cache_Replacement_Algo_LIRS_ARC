# Answer Key

Answers for the worksheets in `MANUAL_TRACING_GUIDE.md`. Every value was verified against the simulator.

**Try the worksheets yourself first before looking here.**

---

## Worksheet 1 — ARC: Cases I and IV

**Capacity:** 3 | **Trace:** A B C A B D A | **H/M:** `MMMHHMH`

| Step | Access | Case | H/M | p | T1 (LRU→MRU) | T2 (LRU→MRU) | B1 | B2 |
|------|--------|------|-----|---|---|---|---|---|
| 1 | A | IV | M | 0 | [A] | [] | [] | [] |
| 2 | B | IV | M | 0 | [A, B] | [] | [] | [] |
| 3 | C | IV | M | 0 | [A, B, C] | [] | [] | [] |
| 4 | A | I (T1) | H | 0 | [B, C] | [A] | [] | [] |
| 5 | B | I (T1) | H | 0 | [C] | [A, B] | [] | [] |
| 6 | D | IV | M | 0 | [D] | [A, B] | [C] | [] |
| 7 | A | I (T2) | H | 0 | [D] | [B, A] | [C] | [] |

**Explanation:**
- Steps 1-3: Cache fills with T1 = [A, B, C]. All Case IV (brand new pages, cache not yet full or just filling).
- Step 4: A is in T1 → Case I hit. Delete from T1, insert at MRU of T2.
- Step 5: B is in T1 → Case I hit. Same process.
- Step 6: D is new. |T1|+|B1| = 1 < c. Total = 3 = c, l1+l2 = 3 ≥ c. REPLACE(D, 0): |T1| = 1 > p = 0 → evict LRU of T1 (C) to B1. Insert D at MRU of T1.
- Step 7: A is in T2 → Case I hit. Move to MRU of T2.

---

## Worksheet 2 — ARC: Case II (B1 ghost hits)

**Capacity:** 3 | **Trace:** A B A C D B C | **H/M:** `MMHMMMM`

| Step | Access | Case | H/M | p | T1 (LRU→MRU) | T2 (LRU→MRU) | B1 | B2 |
|------|--------|------|-----|---|---|---|---|---|
| 1 | A | IV | M | 0 | [A] | [] | [] | [] |
| 2 | B | IV | M | 0 | [A, B] | [] | [] | [] |
| 3 | A | I (T1) | H | 0 | [B] | [A] | [] | [] |
| 4 | C | IV | M | 0 | [B, C] | [A] | [] | [] |
| 5 | D | IV | M | 0 | [C, D] | [A] | [B] | [] |
| 6 | B | II | M | 1 | [D] | [A, B] | [C] | [] |
| 7 | C | II | M | 2 | [D] | [B, C] | [] | [A] |

**Explanation:**
- Step 5: REPLACE(D, 0): |T1| = 2 > p = 0 → evict LRU of T1 (B) to B1.
- Step 6: B found in B1 → Case II. δ = max(1, |B2|/|B1|) = 1. p = min(0+1, 3) = 1. REPLACE(B, 1): B is not in B2. |T1| = 2 > p = 1 → evict LRU of T1 (C) to B1. Delete B from B1. Insert B at MRU of T2.
- Step 7: C found in B1 → Case II again. δ = 1. p = min(1+1, 3) = 2. REPLACE(C, 2): |T1| = 1, p = 2. |T1| > p? No. |T1| = p? No. Else: evict LRU of T2 (A) to B2. Delete C from B1. Insert C at MRU of T2.
- Notice: p climbed 0 → 1 → 2 through consecutive B1 ghost hits.

---

## Worksheet 3 — ARC: Case III (B2 ghost hit)

**Capacity:** 3 | **Trace:** A B A C D B E A | **H/M:** `MMHMMMMM`

| Step | Access | Case | H/M | p | T1 (LRU→MRU) | T2 (LRU→MRU) | B1 | B2 |
|------|--------|------|-----|---|---|---|---|---|
| 1 | A | IV | M | 0 | [A] | [] | [] | [] |
| 2 | B | IV | M | 0 | [A, B] | [] | [] | [] |
| 3 | A | I (T1) | H | 0 | [B] | [A] | [] | [] |
| 4 | C | IV | M | 0 | [B, C] | [A] | [] | [] |
| 5 | D | IV | M | 0 | [C, D] | [A] | [B] | [] |
| 6 | B | II | M | 1 | [D] | [A, B] | [C] | [] |
| 7 | E | IV | M | 1 | [D, E] | [B] | [C] | [A] |
| 8 | A | III | M | 0 | [E] | [B, A] | [C, D] | [] |

**Explanation:**
- Steps 1-6: Same as Worksheet 2 through the B1 ghost hit.
- Step 7: E is new (Case IV). |T1|+|B1| = 2 < c. Total = 5, l1+l2 = 5 ≥ c. REPLACE(E, 1): |T1| = 1, p = 1. |T1| > p? No. |T1| = p = 1, and E in B2? No. Else: evict LRU of T2 (A) to B2.
- Step 8: **A found in B2 → Case III.** δ = max(1, |B1|/|B2|) = max(1, 1/1) = 1. p = max(1−1, 0) = 0. REPLACE(A, 0): A in B2, |T1| = 2 > p = 0 → evict LRU of T1 (D) to B1. Delete A from B2. Insert A at MRU of T2.
- The full cycle: p rose to 1 via Case II (step 6), then fell back to 0 via Case III (step 8).

---

## Worksheet 4 — LIRS: Warm-up, LIR hit, pruning

**Capacity:** 3 (L_lirs=2, L_hirs=1) | **Trace:** A B C A D B | **H/M:** `MMMHMH`

| Step | Access | Event | H/M | S (bottom→top) | Q | n_lir | Prune? |
|------|--------|-------|-----|-----------------|---|-------|--------|
| 1 | A | Warm-up: LIR | M | [A(L)] | [] | 1 | No |
| 2 | B | Warm-up: LIR | M | [A(L), B(L)] | [] | 2 | No |
| 3 | C | Miss: new → res HIR | M | [A(L), B(L), C(H)] | [C] | 2 | No |
| 4 | A | Hit LIR (was bottom) | H | [B(L), C(H), A(L)] | [C] | 2 | Yes: B is LIR → stop |
| 5 | D | Miss: evict C, D → res HIR | M | [B(L), C(N), A(L), D(H)] | [D] | 2 | No |
| 6 | B | Hit LIR (was bottom) | H | [A(L), D(H), B(L)] | [D] | 2 | Yes: remove C(N). A(L) → stop |

**Explanation:**
- Steps 1-2: Warm-up. Each miss enters as LIR.
- Step 3: n_lir = L_lirs = 2, warm-up over. C enters as resident HIR on S and Q.
- Step 4: A is LIR in S at bottom. Move to top. Prune: new bottom B is LIR → done.
- Step 5: Cache full (3 residents). Evict front of Q = C. C is in S → becomes non-resident HIR. D enters as resident HIR.
- Step 6: B is LIR at bottom. Move to top. Prune: bottom is C(non-resident) → remove and forget. New bottom A is LIR → done. Pruning work = 1.

---

## Worksheet 5 — LIRS: HIR-in-S promotion, LIR demotion

**Capacity:** 3 (L_lirs=2, L_hirs=1) | **Trace:** A B C A C E C | **H/M:** `MMMHHMH`

| Step | Access | Event | H/M | S (bottom→top) | Q | n_lir | Prune? |
|------|--------|-------|-----|-----------------|---|-------|--------|
| 1 | A | Warm-up: LIR | M | [A(L)] | [] | 1 | No |
| 2 | B | Warm-up: LIR | M | [A(L), B(L)] | [] | 2 | No |
| 3 | C | Miss: new → res HIR | M | [A(L), B(L), C(H)] | [C] | 2 | No |
| 4 | A | Hit LIR (was bottom) | H | [B(L), C(H), A(L)] | [C] | 2 | Yes: B(L) → stop |
| 5 | C | Hit res HIR **in S** → promote | H | [A(L), C(L)] | [B] | 2 | Yes: A(L) → stop |
| 6 | E | Miss: evict B, E → res HIR | M | [A(L), C(L), E(H)] | [E] | 2 | No |
| 7 | C | Hit LIR | H | [A(L), E(H), C(L)] | [E] | 2 | No (C not bottom) |

**Step 5 in detail:** C is resident HIR and present in S → **promote to LIR**. Move C to top of S. Remove C from Q. n_lir temporarily = 3. Demote bottom LIR (B): B becomes resident HIR, removed from S, added to end of Q. S = [A(L), C(L)], Q = [B]. Prune: bottom A is LIR → done. n_lir = 2.

**Step 6:** Cache full (A, C are LIR = 2 residents; B is res HIR = 1 → total 3). Evict front of Q = B. B is not in S → completely forgotten. E enters as resident HIR.

---

## Worksheet 6 — LIRS: Non-resident HIR promotion

**Capacity:** 4 (L_lirs=3, L_hirs=1) | **Trace:** A B C D E C D F D | **H/M:** `MMMMMHMMH`

| Step | Access | Event | H/M | S (bottom→top) | Q | n_lir | Prune? |
|------|--------|-------|-----|-----------------|---|-------|--------|
| 1 | A | Warm-up: LIR | M | [A(L)] | [] | 1 | No |
| 2 | B | Warm-up: LIR | M | [A(L), B(L)] | [] | 2 | No |
| 3 | C | Warm-up: LIR | M | [A(L), B(L), C(L)] | [] | 3 | No |
| 4 | D | Miss: new → res HIR | M | [A(L), B(L), C(L), D(H)] | [D] | 3 | No |
| 5 | E | Miss: evict D, E → res HIR | M | [A(L), B(L), C(L), D(N), E(H)] | [E] | 3 | No |
| 6 | C | Hit LIR | H | [A(L), B(L), D(N), E(H), C(L)] | [E] | 3 | No |
| 7 | D | Miss: D in S as nonres → promote | M | [B(L), E(N), C(L), D(L)] | [A] | 3 | Yes |
| 8 | F | Miss: evict A, F → res HIR | M | [B(L), E(N), C(L), D(L), F(H)] | [F] | 3 | No |
| 9 | D | Hit LIR | H | [B(L), E(N), C(L), F(H), D(L)] | [F] | 3 | No |

**Step 7 in detail:** Cache full (4 residents: A,B,C LIR + E res HIR). Evict front of Q = E. E is in S → becomes non-resident. Resident = 3. Now D is in S as non-resident HIR → **promote to LIR**. D to top of S. n_lir temporarily = 4. Demote bottom LIR (A): A → res HIR, removed from S, added to end of Q. Prune: new bottom B is LIR → done. n_lir = 3. Resident = 4 (B,C,D LIR + A res HIR).

**Step 8:** Cache full. Evict front of Q = A. A is not in S → forgotten. F enters as resident HIR.

This is the mechanism that gives LIRS its loop resistance: blocks returning from non-resident status in S get promoted to LIR, protecting them from future scans.
