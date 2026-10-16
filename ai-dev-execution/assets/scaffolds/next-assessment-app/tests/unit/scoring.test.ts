import { test } from 'node:test'
import assert from 'node:assert/strict'
import { scoreAnswers } from '../../lib/scoring.ts'
test('rejects empty, invalid values, duplicates and unsafe weights', () => {
  for (const answers of [[], [{questionId:'a',value:0}], [{questionId:'a',value:6}], [{questionId:'a',value:2.5}], [{questionId:'a',value:NaN}], [{questionId:'a',value:3,weight:0}], [{questionId:'a',value:3,weight:-1}], [{questionId:'a',value:3,weight:Infinity}], [{questionId:'a',value:3},{questionId:'a',value:4}]]) assert.throws(() => scoreAnswers(answers))
})
test('reverse and weighted scoring is exact', () => {
  assert.deepEqual(scoreAnswers([{questionId:'a',value:1,reverse:true,weight:3},{questionId:'b',value:1,weight:1}]), {rawAverage:4,normalized:75,level:4})
})
test('exact level thresholds use normalized rounded score', () => {
 for(const [percent,level] of [[20,1],[21,2],[40,2],[41,3],[60,3],[61,4],[80,4],[81,5]]) {
  const score=scoreAnswers([{questionId:'low',value:1,weight:100-percent},{questionId:'high',value:5,weight:percent}])
  assert.equal(score.normalized,percent);assert.equal(score.level,level)
 }
})
test('normalization endpoints and level boundaries', () => {
  for (const [value, normalized, level] of [[1,0,1],[2,25,2],[3,50,3],[4,75,4],[5,100,5]]) assert.deepEqual(scoreAnswers([{questionId:'a',value}]),{rawAverage:value,normalized,level})
})
