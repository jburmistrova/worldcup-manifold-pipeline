# ADR-0005: ELT, not ETL, transformation lives in dbt, not Spark

**Status:** Accepted
**Date:** 2026-07-30

## Context

The original plan (see [ADR-0002](0002-spark-despite-small-data-volume.md) and `docs/architecture.md` as first written) had Spark doing the real analytical work (reconstructing per-market probability-over-time, computing volume-weighted average probability, flagging repricing jumps) *before* landing the result, with dbt transforming again afterward. That's an unintentional hybrid, not a deliberate one, and it leaves dbt without clearly meaningful work: if Spark already computed the real answer, dbt's models just wrap a finished result.

Clarifying what actually distinguishes ETL from ELT resolved this. Whether raw data lands somewhere before transformation happens isn't the real test: a real example came up directly. Loading raw data into a `_raw` table and then transforming it with external Python into a `_transformed` table *looks* ELT-shaped (data lands before transformation) but is still ETL, because the transform runs in an external processing layer, not the destination's own compute. IBM and AWS's own definitions confirm this is the actual distinguishing factor: ETL transforms in a separate engine (often via a staging area); ELT transforms using the destination warehouse's native compute (SQL) [1][2]. dbt exists specifically to be that "T." It assumes raw(ish) data is already in the warehouse and does all its work in testable, documented SQL models [3][4].

By that test, the original plan was ETL with an ELT-shaped diagram: Spark (external compute) doing the transforming, regardless of what landed before or after it.

## Decision

Bound Spark strictly to **extract + load**: parsing Manifold's nested JSON bet data at scale across hundreds of markets, flattening and typing it into clean, partitioned Parquet. No business logic.

All business-logic transformation (probability-over-time reconstruction, volume-weighted average probability, repricing-jump detection, and the full staging -> intermediate -> marts layering) happens in **dbt SQL models**, run against the warehouse.

## Consequences

**Gained:** a genuinely earned ELT pattern, not one that only looks like it from the diagram. dbt gets the real, meaningful work it's actually designed for. Spark's role becomes legitimate in its own right, distributed parsing/flattening of large volumes of semi-structured JSON across many markets, rather than redundantly re-doing SQL-shaped work an external engine didn't need to do.

**Changed:** [ADR-0002](0002-spark-despite-small-data-volume.md)'s description of *what* Spark computes is now narrower than originally written there. That ADR is being updated to point here rather than duplicate this reasoning.

**Still true:** the honest caveat from ADR-0002 stands regardless of this split. The data volume is small enough that none of this, Spark or dbt, strictly needs distributed compute to run correctly. The value is in building the pattern.

## References

1. IBM. *ELT vs. ETL: What's the Difference?* https://ibm.com/think/topics/elt-vs-etl
2. AWS. *What is ETL?* https://aws.amazon.com/what-is/etl/
3. dbt Labs. *Data transformation vs ETL.* https://www.getdbt.com/blog/data-transformation-vs-etl
4. dbt Labs. *Understanding ELT: extract, load, transform.* https://www.getdbt.com/blog/extract-load-transform
