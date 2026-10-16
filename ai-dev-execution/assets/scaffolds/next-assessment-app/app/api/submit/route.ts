import { validateSubmission, PublicError } from '../../../lib/assessment'
import { store, DuplicateError } from '../../../lib/store'
import { sameOrigin, jsonBody, failure, throttle, privateHeaders } from '../../../lib/security'
export const runtime='nodejs'
export async function POST(request:Request) {
 try {
  sameOrigin(request);throttle('submit',100)
  const submission=validateSubmission(await jsonBody(request))
  try {await store.insert(submission)}catch(e){if(e instanceof DuplicateError)throw new PublicError('이미 제출한 학년·반·번호입니다. 재응답은 관리자에게 삭제를 요청하세요.',409);throw e}
  return Response.json({id:submission.id,scores:submission.scores,scoringVersion:submission.scoringVersion},{status:201,headers:privateHeaders})
 } catch(e){return failure(e)}
}
