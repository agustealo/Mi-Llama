import { groundingItemsFromProposal } from './grounding_review_contract.js'

function contextFor(contexts, citationId) {
  if (contexts instanceof Map) return contexts.get(citationId) || null
  return contexts?.[citationId] || null
}

function reviewedTime(proposal) {
  return proposal?.reviewed_at || proposal?.updated_at || proposal?.created_at || ''
}

function citationClosureStatus(item, contexts, documentId) {
  const context = contextFor(contexts, item.citation_id)
  const insertedHere =
    context?.insertion && String(context.insertion.document_id) === String(documentId)
  if (insertedHere) return 'inserted'
  if (context?.citation?.status === 'rejected') return 'rejected'
  return 'pending'
}

function manuscriptLocationFor(proposal, draftText) {
  const start = proposal?.selection_start
  const proposedText = proposal?.proposed_text
  if (
    !Number.isInteger(start) ||
    start < 0 ||
    typeof proposedText !== 'string' ||
    proposedText.length === 0
  ) {
    return { state: 'changed', start: null, end: null }
  }
  if (draftText.slice(start, start + proposedText.length) === proposedText) {
    return { state: 'exact', start, end: start + proposedText.length }
  }

  const first = draftText.indexOf(proposedText)
  if (first >= 0 && first === draftText.lastIndexOf(proposedText)) {
    return { state: 'relocated', start: first, end: first + proposedText.length }
  }
  return { state: 'changed', start: null, end: null }
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

      const location = manuscriptLocationFor(proposal, draft.plain_text)
      return {
        proposalId: proposal.id,
        operation: proposal.operation,
        baseDraftVersion: proposal.base_draft_version,
        reviewedAt: reviewedTime(proposal),
        manuscriptState: location.state,
        manuscriptStart: location.start,
        manuscriptEnd: location.end,
        citations: unique,
      }
    })
    .filter(Boolean)
    .sort((a, b) => b.reviewedAt.localeCompare(a.reviewedAt))
}

export function documentProvenanceHealth(obligations, contexts, documentId) {
  if (!Array.isArray(obligations) || !documentId) {
    return {
      totalGroundedEdits: 0,
      fullyCitedEdits: 0,
      openCitationEdits: 0,
      changedAfterGrounding: 0,
      counterevidenceEdits: 0,
      items: [],
    }
  }

  const items = obligations.map((obligation) => {
    const citations = obligation.citations.map((item) => ({
      ...item,
      closureStatus: citationClosureStatus(item, contexts, documentId),
    }))
    const openCitations = citations.filter((item) => item.closureStatus !== 'inserted')
    return {
      ...obligation,
      citations,
      openCitationCount: openCitations.length,
      fullyCited: openCitations.length === 0,
      hasCounterevidence: citations.some((item) => item.stance === 'contradicts'),
    }
  })

  return {
    totalGroundedEdits: items.length,
    fullyCitedEdits: items.filter((item) => item.fullyCited).length,
    openCitationEdits: items.filter((item) => !item.fullyCited).length,
    changedAfterGrounding: items.filter((item) => item.manuscriptState === 'changed').length,
    counterevidenceEdits: items.filter((item) => item.hasCounterevidence).length,
    items,
  }
}

export function unresolvedCitationObligations(obligations, contexts, documentId) {
  if (!Array.isArray(obligations) || !documentId) return []

  const unresolved = []
  for (const obligation of obligations) {
    const citations = obligation.citations.map((item) => ({
      ...item,
      closureStatus: citationClosureStatus(item, contexts, documentId),
    }))
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

export function documentProvenanceFingerprint(health, unresolved) {
  if (!health?.totalGroundedEdits) return null
  const summary = [
    health.totalGroundedEdits,
    health.fullyCitedEdits,
    health.openCitationEdits,
    health.changedAfterGrounding,
    health.counterevidenceEdits,
  ].join(':')
  const itemIdentity = health.items
    .map((item) =>
      [
        item.proposalId,
        item.manuscriptState,
        item.manuscriptStart ?? 'none',
        item.manuscriptEnd ?? 'none',
        item.openCitationCount,
        item.hasCounterevidence ? 'counter' : 'plain',
      ].join(':'),
    )
    .join('|')
  return `${summary}::${itemIdentity}::${citationClosureFingerprint(unresolved) || 'closed'}`
}
