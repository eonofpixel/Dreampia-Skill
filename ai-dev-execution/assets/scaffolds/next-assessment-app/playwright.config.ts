import { defineConfig } from '@playwright/test'
import { randomBytes } from 'node:crypto'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
const port=process.env.DREAMPIA_UI_PORT ?? '31947'
const origin=`http://127.0.0.1:${port}`
// Ephemeral synthetic credentials, passed only to the isolated child server/tests.
process.env.UI_TEST_ADMIN=process.env.UI_TEST_ADMIN ?? randomBytes(32).toString('hex')
process.env.UI_TEST_CODE=process.env.UI_TEST_CODE ?? randomBytes(12).toString('hex')
export default defineConfig({
 testDir:'./tests/ui',fullyParallel:false,workers:1,timeout:60000,
 reporter:[['list']],use:{baseURL:origin,screenshot:'only-on-failure'},
 webServer:{command:`npm run start -- --port ${port}`,url:origin,reuseExistingServer:false,timeout:120000,
  env:{ASSESSMENT_ADMIN_SECRET:process.env.UI_TEST_ADMIN,ASSESSMENT_ACCESS_CODE:process.env.UI_TEST_CODE,ASSESSMENT_EXPIRES_AT:'2099-01-01T00:00:00Z',ASSESSMENT_DATA_DIR:mkdtempSync(join(tmpdir(),'assessment-ui-data-'))}},
 projects:[{name:'mobile',use:{viewport:{width:390,height:844}}},{name:'tablet',use:{viewport:{width:820,height:1180}}},{name:'desktop',use:{viewport:{width:1366,height:768}}}]
})
