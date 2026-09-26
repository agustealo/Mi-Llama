export function groundingItemsFromProposal(proposal) {
  const grounding = proposal?.context_manifest?.grounding
  if (!grounding || grounding.version !== 1 || !Array.isArray(grounding.citations)) return []
  return grounding.citations.filter((item) => {
    return Boolean(
      item &&
        typeof item.citation_id === 'string' &&
        typeof item.source_filename === 'string' &&
        typeof item.stance === 'string' &&
        typeof item.content_sha256 === 'string',
    )
  })
}

export function groundingSummary(proposal) {
  const items = groundingItemsFromProposal(proposal)
  const counts = { supports: 0, contradicts: 0, context: 0, other: 0 }
  for (const item of items) {
    if (item.stance === 'supports') counts.supports += 1
    else if (item.stance === 'contradicts') counts.contradicts += 1
    else if (item.stance === 'context') counts.context += 1
    else counts.other += 1
  }
  return {
    items,
    counts,
    label: `support ${counts.supports} · contradict ${counts.contradicts} · context ${counts.context}`,
  }
}

export function activeProposalForDraft(proposals, draftVersion) {
  if (!Array.isArray(proposals) || !Number.isInteger(draftVersion)) return null
  return (
    proposals.find(
      (proposal) => proposal?.status === 'proposed' && proposal?.base_draft_version === draftVersion,
    ) || null
  )
}

export function groundingFingerprint(proposal) {
  const items = groundingItemsFromProposal(proposal)
  if (!proposal?.id || items.length === 0) return null
  return `${proposal.id}:${items.map((item) => `${item.citation_id}:${item.content_sha256}`).join('|')}`
}
