import bank from '../data/questions.sample.json' with {type:'json'}
import { scoreAnswers } from './scoring.ts'
import type { ScoreResult } from './scoring.ts'
import { randomUUID, timingSafeEqual } from 'node:crypto'
export { bank }
export class PublicError extends Error {
  status: number
  constructor(message: string, status = 400) { super(message); this.status = status }
}
export function validateCode(code: unknown) {
 const expected = process.env.ASSESSMENT_ACCESS_CODE
 const expires = Date.parse(process.env.ASSESSMENT_EXPIRES_AT ?? '')
 if (!expected || expected.length < 8 || !Number.isFinite(expires)) throw new PublicError('진단 설정이 필요합니다. 관리자에게 문의하세요.',503)
 if (Date.now() >= expires || typeof code !== 'string' || code.length > 128 || Buffer.byteLength(code) !== Buffer.byteLength(expected) || !timingSafeEqual(Buffer.from(code),Buffer.from(expected))) throw new PublicError('진단 코드가 올바르지 않거나 만료되었습니다.',403)
}
export function validateSubmission(input: unknown) {
 if (!input || typeof input !== 'object' || Array.isArray(input)) throw new PublicError('입력 내용을 확인하세요.')
 const data = input as Record<string,unknown>
 if (Object.keys(data).sort().join(',') !== 'answers,classNumber,code,grade,studentNumber') throw new PublicError('허용되지 않은 입력 항목입니다.')
 validateCode(data.code)
 for (const [key,max] of [['grade',12],['classNumber',50],['studentNumber',60]] as const) if (typeof data[key] !== 'number' || !Number.isInteger(data[key]) || (data[key] as number) < 1 || (data[key] as number) > max) throw new PublicError('학년·반·번호 범위를 확인하세요.')
 if (!data.answers || typeof data.answers !== 'object' || Array.isArray(data.answers)) throw new PublicError('모든 문항에 응답하세요.')
 const answers = data.answers as Record<string,number>
 if (Object.keys(answers).sort().join(',') !== bank.questions.map(q=>q.id).sort().join(',')) throw new PublicError('모든 문항에 응답하세요.')
 const mapped = bank.questions.map(q=>({...q,questionId:q.id,value:answers[q.id]}))
 const scores: Record<string,ScoreResult> = {}
 try {
  scores.total=scoreAnswers(mapped)
  for(const domain of Object.keys(bank.domains)) scores[domain]=scoreAnswers(mapped.filter(q=>q.domain===domain))
 } catch {throw new PublicError('응답은 1~5의 정수여야 합니다.')}
 return { id:randomUUID(),createdAt:new Date().toISOString(),sessionId:bank.sessionId,grade:data.grade as number,classNumber:data.classNumber as number,studentNumber:data.studentNumber as number,answers,scoringVersion:bank.scoringVersion,scores }
}
