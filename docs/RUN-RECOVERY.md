# RUN/2 recovery (PoC)

The RUN directory and its SHA-256-verified manifest are the authoritative
publication evidence. SQLite and `project.json` are separate indexes and do
not participate in a shared filesystem transaction.

After an interrupted RUN publication, **stop all writers** and run:

```sh
fairmorph-engine reconcile-runs --project /path/to/project
fairmorph-engine verify-project --project /path/to/project
```

The explicit recovery operation validates every completed RUN, then inserts
missing catalog entries and updates the project index. It is idempotent and
does not rerun transformations or silently delete data. Invalid completed RUNs,
missing indexed RUNs, unsafe directory entries, or checksum mismatches cause
recovery to stop without accepting the corrupted RUN. Incomplete
`.pending-*` directories are retained for investigation, never promoted.

**Limitations:** This is PoC-level reconciliation, not a fully crash-atomic
multi-store transaction. No cross-process writer lock or power-loss durability
guarantee is implemented. A crash during reconciliation can require running
the command again. The operation must not run concurrently with import,
mapping execution, export, or another recovery process. The final acceptance
must include fault-injection testing at publication boundaries.

## Fault-injection acceptance matrix

The mandatory generic Engine CI runs `tests/test_run_publication_fault_injection.py`
with synthetic input, independently of the optional CS-PHOC reference workflow.

| Injected boundary | Expected behavior |
| --- | --- |
| Staging-to-final directory rename fails | No published RUN or index entry; pending diagnostics retained |
| `project.json` replacement fails | SQLite transaction rolls back; published directory moves back to pending |
| Crash after completed directory, before either index | Explicit reconciliation reconstructs both indexes |
| Crash with only one index durable | Explicit reconciliation repairs the missing index |
| Recovery index replacement fails | SQLite changes roll back; a later retry succeeds |
| Published manifest missing or artifacts corrupted | Fail closed without dropping catalog/index references |
| Second reconciliation | Idempotent; no new RUN entries |

These are deterministic exception and persisted-state simulations, **not**
physical power-loss tests. Passing the matrix is necessary for PoC acceptance,
but does not establish fsync-level durability or concurrent-writer safety.
