import { groundingItemsFromProposal } from './grounding_review_contract.js'

function contextFor(contexts, citationId) {
  if (contexts instanceof Map) return contexts.get(citationId) || null
  return contexts?.[citationId] || null
}

function reviewedTime(proposal) {
  return proposal?.reviewed_at || proposal?.updated_at || proposal?.created_at || ''
}

export function acceptedGroundingObligations(proposals, draft) {
  if (!Array.isArray(proposals) || typeof draft?.plain_text !== 'string') return []

  return proposals
    .filter((proposal) => proposal?.status === 'accepted')
    .map((proposal) => {
      const items = groundingItemsFromProposal(proposal)
      if (items.length === 0) return null

      const unique = []
      const seen = new Set()
      for (const item of items) {
        if (seen.has(item.citation_id)) continue
        seen.add(item.citation_id)
        unique.push(item)
      }

      const start = proposal.selection_start
      const proposedText = proposal.proposed_text
      const exact =
        Number.isInteger(start) &&
        start >= 0 &&
        typeof proposedText === 'string' &&
        proposedText.length > 0 &&
        draft.plain_text.slice(start, start + proposedText.length) === proposedText

      return {
        proposalId: proposal.id,
        operation: proposal.operation,
        baseDraftVersion: proposal.base_draft_version,
        reviewedAt: reviewedTime(proposal),
        manuscriptState: exact ? 'exact' : 'changed',
        citations: unique,
      }
    })
    .filter(Boolean)
    .sort((a, b) => b.reviewedAt.localeCompare(a.reviewedAt))
}

export function unresolvedCitationObligations(obligations, contexts, documentId) {
  if (!Array.isArray(obligations) || !documentId) return []

  const unresolved = []
  for (const obligation of obligations) {
    const citations = obligation.citations.map((item) => {
      const context = contextFor(contexts, item.citation_id)
      const insertedHere =
        context?.insertion && String(context.insertion.document_id) === String(documentId)
      const status = insertedHere
        ? 'inserted'
        : context?.citation?.status === 'rejected'
          ? 'rejected'
          : 'pending'
      return { ...item, closureStatus: status }
    })
    const openCitations = citations.filter((item) => item.closureStatus !== 'inserted')
    if (openCitations.length === 0) continue
    unresolved.push({
      ...obligation,
      citations,
      openCitations,
      pendingCount: openCitations.filter((item) => item.closureStatus === 'pending').length,
      rejectedCount: openCitations.filter((item) => item.closureStatus === 'rejected').length,
    })
  }
  return unresolved
}

export function citationClosureFingerprint(obligations) {
  if (!Array.isArray(obligations) || obligations.length === 0) return null
  return obligations
    .map((obligation) => {
      const citations = obligation.openCitations
        .map((item) => `${item.citation_id}:${item.closureStatus}:${item.content_sha256}`)
        .join('|')
      return `${obligation.proposalId}:${obligation.manuscriptState}:${citations}`
    })
    .join('||')
}
