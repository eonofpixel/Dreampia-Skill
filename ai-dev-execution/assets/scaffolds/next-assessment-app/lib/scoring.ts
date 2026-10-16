export type Answer = { questionId: string; value: number; reverse?: boolean; weight?: number }
export type ScoreResult = { rawAverage: number; normalized: number; level: number }
export function scoreAnswers(answers: Answer[]): ScoreResult {
  if (!Array.isArray(answers) || !answers.length) throw new Error('Answers required')
  const ids = new Set<string>()
  for (const a of answers) {
    if (!a || typeof a.questionId !== 'string' || !a.questionId || ids.has(a.questionId) || !Number.isInteger(a.value) || a.value < 1 || a.value > 5 || (a.reverse !== undefined && typeof a.reverse !== 'boolean') || !Number.isFinite(a.weight ?? 1) || (a.weight ?? 1) <= 0) throw new Error('Invalid answer')
    ids.add(a.questionId)
  }
  const totalWeight = answers.reduce((sum,a) => sum + (a.weight ?? 1),0)
  const weighted = answers.reduce((sum,a) => sum + (a.reverse ? 6-a.value : a.value)*(a.weight ?? 1),0)
  if (!Number.isFinite(totalWeight) || !Number.isFinite(weighted)) throw new Error('Invalid weights')
  const rawAverage = weighted / totalWeight
  const normalized = Math.round((rawAverage-1)/4*100)
  return { rawAverage, normalized, level: normalized >= 81 ? 5 : normalized >= 61 ? 4 : normalized >= 41 ? 3 : normalized >= 21 ? 2 : 1 }
}
