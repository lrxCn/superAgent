# SuperAgent Architecture Maps

Maps in this directory describe the **current implemented** runtime (tasks 01–14). They are generated from `src/agent/` and `tests/`, not from future proposals.

| Map | File | Contents |
|-----|------|----------|
| Runtime graph | [runtime-graph.md](./runtime-graph.md) | LangGraph nodes, conditional edges, execution paths |
| Module map | [module-map.md](./module-map.md) | Source modules, responsibilities, test locations |
| State contract | [state-contract.md](./state-contract.md) | `AgentState` fields and downstream consumers |

When code changes topology or contracts, update these maps in the same PR as the implementation.
