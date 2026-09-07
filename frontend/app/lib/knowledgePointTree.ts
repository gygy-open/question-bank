import type { KnowledgePoint } from '@/types'

export interface KnowledgePointNode extends KnowledgePoint {
  children: KnowledgePointNode[]
}

export function buildKnowledgePointTree(points: KnowledgePoint[]): KnowledgePointNode[] {
  const map = new Map<number, KnowledgePointNode>()
  const roots: KnowledgePointNode[] = []

  points.forEach((kp) => {
    map.set(kp.id, { ...kp, children: [] })
  })

  points.forEach((kp) => {
    const node = map.get(kp.id)!
    const parent = kp.parent_id ? map.get(kp.parent_id) : undefined
    if (parent) parent.children.push(node)
    else roots.push(node)
  })

  return roots
}

// Keep a node's ancestor chain visible even when only a descendant matches the query.
export function filterKnowledgePointTree(tree: KnowledgePointNode[], query: string): KnowledgePointNode[] {
  const q = query.trim().toLowerCase()
  if (!q) return tree

  function filterNode(node: KnowledgePointNode): KnowledgePointNode | null {
    const selfMatches = node.name.toLowerCase().includes(q)
    const filteredChildren = node.children
      .map(filterNode)
      .filter((n): n is KnowledgePointNode => n !== null)
    if (!selfMatches && filteredChildren.length === 0) return null
    return { ...node, children: filteredChildren }
  }

  return tree.map(filterNode).filter((n): n is KnowledgePointNode => n !== null)
}
