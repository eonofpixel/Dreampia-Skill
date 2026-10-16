import { test } from 'node:test'
import assert from 'node:assert/strict'
import { validateSubmission } from '../../lib/assessment.ts'
import { adminToken, isAdmin, sameOrigin } from '../../lib/security.ts'
test('same-origin uses loopback Host instead of Next internal URL and rejects foreign origins',()=>{
 assert.doesNotThrow(()=>sameOrigin(new Request('http://localhost:31947/api/access',{headers:{host:'127.0.0.1:31947',origin:'http://127.0.0.1:31947'}})))
 for(const origin of ['http://evil.invalid','http://127.0.0.1:31948','null','']) assert.throws(()=>sameOrigin(new Request('http://localhost:31947/api/access',{headers:{host:'127.0.0.1:31947',origin}})))
 assert.throws(()=>sameOrigin(new Request('http://evil.invalid/api/access',{headers:{host:'evil.invalid',origin:'http://evil.invalid'}})))
})
const valid = {code:'test-access-only',grade:1,classNumber:2,studentNumber:3,answers:{Q001:5,Q002:1,Q003:3,Q004:3}}
test('server-controlled scoring and strict identity/question validation',()=>{
 process.env.ASSESSMENT_ACCESS_CODE='test-access-only'
 process.env.ASSESSMENT_EXPIRES_AT='2099-01-01T00:00:00Z'
 const result=validateSubmission(valid)
 assert.equal(result.scores.ai_ethics_security.normalized,100)
 assert.equal(result.scores.career.normalized,50)
 for (const input of [{...valid,code:'wrong'}, {...valid,grade:0}, {...valid,grade:'1'}, {...valid,studentNumber:2.5}, {...valid,answers:{Q001:5}}, {...valid,answers:{...valid.answers,unknown:4}}, {...valid,answers:{...valid.answers,Q002:6}}, {...valid,name:'unwanted'}, {...valid,scores:{total:100}}]) assert.throws(()=>validateSubmission(input))
 process.env.ASSESSMENT_EXPIRES_AT='2000-01-01T00:00:00Z'
 assert.throws(()=>validateSubmission(valid))
 delete process.env.ASSESSMENT_EXPIRES_AT
 assert.throws(()=>validateSubmission(valid))
})
test('admin fails closed, signed token expiry and tampering',()=>{
 delete process.env.ASSESSMENT_ADMIN_SECRET
 assert.equal(isAdmin(new Request('http://localhost')),false)
 assert.throws(()=>adminToken())
 process.env.ASSESSMENT_ADMIN_SECRET='unit-only-secret-with-at-least-32-characters'
 const request=(token:string)=>new Request('http://localhost',{headers:{cookie:`assessment_admin=${token}`}})
 assert.ok(isAdmin(request(adminToken())))
 assert.equal(isAdmin(request(adminToken(0))),false)
 assert.equal(isAdmin(request(adminToken()+'x')),false)
 delete process.env.ASSESSMENT_ADMIN_SECRET
 assert.equal(isAdmin(request('anything')),false)
})
