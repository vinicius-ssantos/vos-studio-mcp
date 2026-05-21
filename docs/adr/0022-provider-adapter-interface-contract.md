# ADR-0022 — Provider adapter interface contract

Status: Accepted  
Date: 2026-05-21

## Context

ADR-0009 decided that provider integrations (Higgsfield, Freepik, Magnific, and manual dashboard) will be implemented as adapters behind a common internal interface. That ADR established the pattern but did not define what the interface actually guarantees — which methods exist, what they receive, what they return, and how errors, rate limits, and cost estimation are handled.

Without a defined contract, each adapter will be implemented inconsistently. Tool handlers will need to know which provider they are calling, defeating the purpose of the adapter pattern. Cost estimation (ADR-0012) and audit logging (ADR-0015) cannot be applied uniformly.

## Decision

All provider adapters must implement the following TypeScript interface:

```typescript
interface ProviderAdapter {
  readonly providerId: string;

  estimateCost(params: GenerationParams): Promise<CostEstimate>;

  generateImage(params: GenerationParams): Promise<GenerationResult>;

  generateVideo(params: GenerationParams): Promise<GenerationResult>;

  checkJobStatus(jobId: string): Promise<JobStatus>;

  prepareManualPack(params: GenerationParams): Promise<ManualPack>;
}
```

**Method contracts:**

- `estimateCost` must return a cost estimate before any paid action is taken. It must never call the provider API — it calculates from local pricing data. If pricing is unknown, it must return a conservative upper-bound estimate with a `uncertain: true` flag.

- `generateImage` and `generateVideo` are only valid for adapters in `api_credits` mode (ADR-0003). Manual dashboard adapters must throw a `NotSupportedError` for these methods.

- `checkJobStatus` returns the current state of an async generation job. For synchronous providers, it may return an immediately resolved result.

- `prepareManualPack` is only valid for adapters in `dashboard_manual` mode (ADR-0003). API adapters may implement it to return a preview of the prompt pack that would be sent, but it must not trigger any generation.

**Shared types:**

```typescript
interface GenerationParams {
  sprintId: string;
  promptVersion: string;      // required per ADR-0013
  presetVersion: string;      // required per ADR-0013
  mode: 'dashboard_manual' | 'api_credits';
  budgetLimit?: BudgetLimit;  // required if mode is api_credits
  approvalToken?: string;     // required if mode is api_credits
}

interface GenerationResult {
  jobId: string;
  status: 'queued' | 'completed' | 'failed';
  assetRef?: AssetReference;  // present if status is completed
  cost?: ActualCost;
}

interface ManualPack {
  prompt: string;
  negativePrompt?: string;
  provider: string;
  model: string;
  settings: Record<string, unknown>;
  checklist: string[];
  namingConvention: string;
  qacreateria: string[];
}
```

## Alternatives considered

- **No shared interface, duck typing**: each tool handler checks the provider type and calls different methods. Rejected because it spreads provider-specific logic into tool handlers and makes cost/audit hooks impossible to apply uniformly.
- **Abstract base class**: adds inheritance complexity in TypeScript. Rejected in favor of a plain interface + composition.
- **GraphQL or REST between MCP and adapters**: over-engineered for an in-process adapter. Rejected.

## Consequences

All five adapters (manual, Higgsfield, Freepik, Magnific, and any future provider) must implement this interface. Adding a new provider means implementing the interface — tool handlers do not need to change.

The interface makes it possible to inject adapters in tests with a mock implementation, improving testability of tool handlers without calling real provider APIs.

The `estimateCost` contract ensures that budget validation (ADR-0012) can be applied at the tool layer before any generation is enqueued, regardless of provider.

## Impact on VOS Studio MCP

- Create `src/services/providers/ProviderAdapter.ts` as the canonical interface definition.
- Create `src/services/providers/ManualDashboardAdapter.ts` as the first implementation, targeting Milestone 2.
- Each provider adapter file in `src/services/providers/` must import and implement `ProviderAdapter`.
- Tool handlers must accept a `ProviderAdapter` instance via dependency injection, not import adapters directly.
- The adapter registry (`src/services/providers/index.ts`) maps `providerId` strings to adapter instances and is the only place where concrete adapters are instantiated.
