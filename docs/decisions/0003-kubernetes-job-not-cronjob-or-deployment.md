# ADR-0003: Kubernetes Job, not CronJob or Deployment — and why Kubernetes at all

**Status:** Accepted
**Date:** 2026-07-30

## Context

The pipeline (ingest → Spark → dbt) runs once, over a tournament that already ended — it's a backfill, not a recurring poll and not a long-running service. For a single person running this once on a local machine, Kubernetes is not technically required either: a bash script would work. This needs to be said plainly, not glossed over, because at company scale there *are* real reasons to prefer Kubernetes (cluster-wide bin-packing across many workloads, automatic recovery when one of many machines fails, one shared operational model instead of every team inventing its own, autoscaling under real load spikes) — but none of those forcing functions exist at "one script, one laptop, one run" scale, and the project will run on a single-node local cluster (minikube/kind) where most of that value proposition doesn't apply anyway.

## Decision

Containerize ingest + Spark + dbt and run them as a Kubernetes **Job**, deliberately, as hands-on practice with a named skill gap — not because the workload requires it.

Within Kubernetes' own primitives, a Job is the correct choice regardless: not a **CronJob** (no recurring schedule — this runs once), not a **Deployment** (doesn't run forever — a Deployment is for services that should always be up, like a matching engine or API).

## Consequences

**Gained:** hands-on practice with the actual K8s primitives that transfer regardless of scale — writing declarative Job specs, automatic retry semantics (`backoffLimit`) instead of a hand-rolled retry loop, enforced resource requests/limits, and the `kubectl` debugging workflow (`describe pod`, reading `CrashLoopBackOff`/`Pending` states) that's what's actually tested in interviews.

**Gave up:** none of Kubernetes' scale-driven value (multi-node scheduling, self-healing across node failures, cluster-wide resource sharing) is demonstrated here — a single-node local cluster can't show it. If asked "did you need Kubernetes for this," the honest answer is no; the value was in the practice, not the workload's requirements.
