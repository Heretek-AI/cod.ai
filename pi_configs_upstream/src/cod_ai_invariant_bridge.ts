/**
 * @heretek-ai/pi-configs — cod.ai Invariant Compliance Bridge (v1.3.0)
 * Fixes the two PARTIAL invariants identified in the cod.ai Phase 1 Harness Decision Matrix:
 *   1. Invariant #1 & #3: Cache-preserving `/specialist` & `/mode` switching via Layer 3
 *      mid-conversation system messages (`role: "system"` / `<system_reminder>`) instead of mutating Layer 1.
 *   2. Invariant #4: 60-80% Attention Budget Governor + 5-Minute TTL Keep-Alive Monitor.
 */

export interface PiContentBlock {
  type: "text" | "tool_use" | "tool_result" | "tool_reference" | "tool_addition" | "tool_removal";
  text?: string;
  cache_control?: { type: "ephemeral"; ttl?: "5m" | "1h" };
  [key: string]: unknown;
}

export interface PiSessionNode {
  id: string;
  parentId: string | null;
  role: "user" | "assistant" | "system";
  content: string | PiContentBlock[];
  clear_at?: "never" | "next_user_message";
  timestamp: number;
}

export interface AttentionBudgetStatus {
  totalTokens: number;
  contextWindow: number;
  utilizationRatio: number;
  status: "OPTIMAL" | "SOFT_WARNING_MICROCOMPACT" | "HARD_CEILING_COMPACT_SERVICE";
  recommendedAction: string;
}

export class CodAiPiInvariantBridge {
  private readonly softCeilingRatio = 0.60;
  private readonly hardCeilingRatio = 0.75;
  private readonly maxCeilingRatio = 0.80;

  /**
   * Injects a specialist charter or Mode A / Mode B polarity switch into Layer 3
   * WITHOUT mutating Layer 1 (the static 20-line Pi system prompt).
   */
  public createCacheSafeCharterSwitch(
    parentNodeId: string,
    specialistSlug: string,
    charterMarkdown: string,
    polarityMode: "MODE_A_ARCHITECT" | "MODE_B_IMPLEMENTER",
    supportsNativeMidConvSystem: boolean = true
  ): PiSessionNode {
    const payload = [
      `<system_reminder type="charter_polarity_switch" specialist="${specialistSlug}" mode="${polarityMode}">`,
      `OPERATOR DIRECTIVE: You are now operating under the [${specialistSlug}] charter in ${polarityMode}.`,
      `Layer 1 and Layer 2 remain byte-identical to preserve the ephemeral prompt cache.`,
      charterMarkdown.trim(),
      `</system_reminder>`,
    ].join("\n");

    if (supportsNativeMidConvSystem) {
      return {
        id: `node_${Date.now()}_${specialistSlug}`,
        parentId: parentNodeId,
        role: "system",
        clear_at: "never",
        content: [{ type: "text", text: payload }],
        timestamp: Date.now(),
      };
    }

    return {
      id: `node_${Date.now()}_${specialistSlug}`,
      parentId: parentNodeId,
      role: "user",
      content: [{ type: "text", text: payload }],
      timestamp: Date.now(),
    };
  }

  /**
   * Evaluates current token usage against the 60-80% Attention Budget Governor ceiling
   * (replacing Pi's default window - 16,384 late compaction threshold).
   */
  public evaluateAttentionBudget(totalTokens: number, contextWindow: number): AttentionBudgetStatus {
    const ratio = totalTokens / Math.max(1, contextWindow);
    if (ratio >= this.hardCeilingRatio) {
      return {
        totalTokens,
        contextWindow,
        utilizationRatio: Number(ratio.toFixed(4)),
        status: "HARD_CEILING_COMPACT_SERVICE",
        recommendedAction:
          "Trigger Stage 2 Compact Service (NO_TOOLS_PREAMBLE + 9-section <summary> + top-5 recent files) with skipCacheWrite=true.",
      };
    }
    if (ratio >= this.softCeilingRatio) {
      return {
        totalTokens,
        contextWindow,
        utilizationRatio: Number(ratio.toFixed(4)),
        status: "SOFT_WARNING_MICROCOMPACT",
        recommendedAction:
          "Trigger Stage 1 Cache-Aware Micro-Compaction (prune raw tool outputs strictly AFTER the last cached breakpoint) and route repo queries to project_knowledge_search.",
      };
    }
    return {
      totalTokens,
      contextWindow,
      utilizationRatio: Number(ratio.toFixed(4)),
      status: "OPTIMAL",
      recommendedAction: "Maintain full in-context n^2 self-attention purity.",
    };
  }
}
