#!/usr/bin/env node
/* Inspect any compiled exploration with an offline browser and capture each view. */
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');
const input=process.argv[2], output=process.argv[3];
if(!input||!output){console.error('Usage: node inspect_exploration.cjs exploration.html output-directory');process.exit(2);}
let chromium;
try{({chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright'));}
catch(error){console.error('Install Playwright in a tool directory and set PLAYWRIGHT_MODULE to its module path. '+error.message);process.exit(2);}
const directory=path.resolve(output);fs.mkdirSync(directory,{recursive:true});
(async()=>{
 const executable=process.env.CHROME_PATH||('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome');
 const browser=await chromium.launch({headless:true,...(fs.existsSync(executable)?{executablePath:executable}:{})});
 const report={input:path.resolve(input),views:[],errors:[],externalRequests:[]};
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1100},deviceScaleFactor:1,offline:true});
  const page=await context.newPage();
  page.on('pageerror',error=>report.errors.push(error.message));
  page.on('request',request=>{if(/^https?:/.test(request.url()))report.externalRequests.push(request.url());});
  await page.goto(pathToFileURL(path.resolve(input)).href);
  await page.waitForFunction(()=>window.exploration&&window.exploration.audit());
  const document=await page.evaluate(()=>exploration.getDocument());
  const initial=await page.evaluate(()=>exploration.getState());
  for(const [index,view] of document.views.entries()){
   await page.evaluate(id=>exploration.setState({view:id}),view.id);
   await page.waitForFunction(()=>!exploration.audit().animating);
   const audit=await page.evaluate(()=>exploration.audit());
   assert.equal(audit.errors,0,view.id+' renders');assert.equal(audit.overflow,false,view.id+' has no horizontal overflow');
   const filename=`${String(index+1).padStart(2,'0')}-${view.id.replace(/[^a-zA-Z0-9_-]/g,'-')}.png`;
   await page.screenshot({path:path.join(directory,filename),fullPage:true});
   report.views.push({id:view.id,...audit,screenshot:filename});
  }
  await page.evaluate(state=>exploration.setState(state),initial);
  if(document.time){
   const earliest=await page.evaluate(()=>DataExplorationCore.frames(exploration.getDocument())[0]);
   await page.evaluate(time=>exploration.seek(time),earliest);
   await page.waitForFunction(()=>!exploration.audit().animating);
   await page.screenshot({path:path.join(directory,'first-frame.png'),fullPage:true});
   const count=await page.evaluate(()=>DataExplorationCore.frames(exploration.getDocument()).length);
   if(count>1){
    await page.evaluate(()=>exploration.play());
    await page.waitForFunction(time=>exploration.getState().time!==time,earliest,{timeout:15000});
    await page.evaluate(()=>exploration.stop());report.playbackAdvanced=true;
   }
  }
  await page.evaluate(state=>exploration.setState(state),initial);
  await page.setViewportSize({width:390,height:844});
  await page.waitForFunction(()=>!exploration.audit().overflow&&!exploration.audit().animating);
  await page.screenshot({path:path.join(directory,'mobile.png'),fullPage:true});
  report.mobile=await page.evaluate(()=>exploration.audit());
  assert.deepEqual(report.errors,[]);assert.deepEqual(report.externalRequests,[]);
 }catch(error){report.failure=error.stack;process.exitCode=1;}
 finally{await browser.close();fs.writeFileSync(path.join(directory,'audit.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));}
})().catch(error=>{console.error(error);process.exitCode=1;});
