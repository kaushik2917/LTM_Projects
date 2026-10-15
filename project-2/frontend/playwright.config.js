import {defineConfig} from '@playwright/test';
import path from 'node:path';
const backend=path.resolve('../backend');
const python=process.platform==='win32'?path.join(backend,'.venv/Scripts/python.exe'):path.join(backend,'.venv/bin/python');
export default defineConfig({
 testDir:'./tests',fullyParallel:false,workers:1,timeout:120000,
 use:{baseURL:'http://127.0.0.1:5174',viewport:{width:1440,height:1000},headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome',screenshot:'only-on-failure'},
 webServer:[
  {command:`"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8001`,cwd:backend,url:'http://127.0.0.1:8001/api/health',reuseExistingServer:false,env:{MOCK_MODE:'true',DATABASE_URL:'sqlite:///./data/browser-tests.db',CORS_ORIGINS:'http://127.0.0.1:5174'},timeout:120000},
  {command:'npm run dev -- --port 5174 --strictPort',url:'http://127.0.0.1:5174',reuseExistingServer:false,env:{CALLSENSE_API_TARGET:'http://127.0.0.1:8001'},timeout:120000}
 ]
});
