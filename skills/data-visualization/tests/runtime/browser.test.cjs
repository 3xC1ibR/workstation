/* End-to-end checks against compiled, portable examples. Requires local Chrome and Playwright. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const input=path.resolve(process.argv[2]||'/opt/projects/output/data-visualization');
const output=path.resolve(process.env.DATA_VISUALIZATION_TEST_OUTPUT||'/tmp/data-observatory-browser/results');
fs.mkdirSync(output,{recursive:true});
const reports=[];
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 try{
  for(const name of ['ai-horizons','midterm-votes']){
   const context=await browser.newContext({viewport:{width:1440,height:1100},deviceScaleFactor:1,offline:true});
   const page=await context.newPage(),errors=[],external=[];
   page.on('pageerror',error=>errors.push(error.message));
   page.on('request',request=>{if(/^https?:/.test(request.url()))external.push(request.url());});
   await page.goto(pathToFileURL(path.join(input,name,'index.html')).href);
   await page.waitForFunction(()=>window.exploration?.audit().chart);
   const defaultState=await page.evaluate(()=>exploration.getState());
   const initial=await page.evaluate(()=>exploration.audit());
   assert.equal(initial.errors,0);assert.equal(initial.overflow,false);
   assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
   await page.screenshot({path:path.join(output,`${name}-desktop.png`),fullPage:true});
   const plot=page.locator('.plot svg');
   const firstMark=plot.locator('[aria-label="dot"] circle').first();
   assert.ok(await firstMark.count(),'visible observation marks');
   await firstMark.click();
   assert.equal((await page.evaluate(()=>exploration.getState())).selected.length,1);
   assert.ok(await page.getByText('Selected observation',{exact:true}).isVisible());
   await page.screenshot({path:path.join(output,`${name}-selected.png`),fullPage:true});
   await page.getByRole('button',{name:'Clear selection',exact:true}).click();
   await page.getByRole('slider',{name:'Observation time',exact:true}).press('Home');
   const earliest=await page.evaluate(()=>exploration.getState().time);
   assert.notEqual(earliest,defaultState.time);
   const firstCount=await page.evaluate(()=>exploration.getRows().length);
   assert.ok(firstCount>0);
   await page.getByRole('button',{name:'Next observed frame',exact:true}).click();
   assert.notEqual(await page.evaluate(()=>exploration.getState().time),earliest);
   await page.getByRole('button',{name:'Play observed frames',exact:true}).click();
   await page.waitForFunction(()=>exploration.audit().playing);
   await page.getByRole('button',{name:'Pause playback',exact:true}).click();
   assert.equal(await page.evaluate(()=>exploration.audit().playing),false);
   await page.getByRole('button',{name:'Reset exploration',exact:true}).click();
   await page.getByRole('searchbox',{name:'Search observations'}).fill('no-such-observation-000');
   assert.ok(await page.getByText('No observations in this view',{exact:true}).isVisible());
   assert.equal(await page.evaluate(()=>exploration.getRows().length),0);
   await page.getByRole('button',{name:'Clear filters',exact:true}).click();
   assert.ok(await page.locator('.plot svg').count());
   const views=await page.evaluate(()=>exploration.getDocument().views.map(view=>({id:view.id,type:view.type,title:view.title})));
   for(const view of views){
    await page.locator(`[data-view="${view.id}"]`).click();
    const audit=await page.evaluate(()=>exploration.audit());assert.equal(audit.errors,0,`${name}/${view.id}`);
    if(view.type!=='table')assert.ok(audit.chart,`${view.id} has SVG`);
    await page.screenshot({path:path.join(output,`${name}-${view.id}.png`),fullPage:true});
   }
   await page.getByRole('button',{name:'Data',exact:true}).click();
   assert.ok(await page.getByRole('table').isVisible());
   const csv=await page.evaluate(()=>exploration.exportCSV());assert.equal(csv.split('\r\n').length,1+initial.rows.visible);
   await page.getByRole('button',{name:'Sources',exact:true}).click();
   assert.ok(await page.getByRole('heading',{name:'Transformation record',exact:true}).isVisible());
   assert.ok(await page.getByRole('heading',{name:'Field dictionary',exact:true}).isVisible());
   await page.getByRole('button',{name:'Chart',exact:true}).click();
   await page.getByRole('button',{name:'Reset exploration',exact:true}).click();
   await page.getByRole('button',{name:'Select region',exact:true}).click();
   const box=await page.locator('.cohort-brush .overlay').boundingBox();assert.ok(box);
   await page.mouse.move(box.x+box.width*.2,box.y+box.height*.2);await page.mouse.down();await page.mouse.move(box.x+box.width*.85,box.y+box.height*.85,{steps:10});await page.mouse.up();
   assert.ok((await page.evaluate(()=>exploration.getState())).brush);
   await page.getByRole('button',{name:'Clear region',exact:true}).click();
   assert.equal((await page.evaluate(()=>exploration.getState())).brush,null);
   await page.getByRole('button',{name:'Reset exploration',exact:true}).click();
   await page.setViewportSize({width:390,height:844});
   await page.waitForFunction(()=>!exploration.audit().overflow);
   await page.screenshot({path:path.join(output,`${name}-mobile.png`),fullPage:true});
   await page.emulateMedia({reducedMotion:'reduce'});
   await page.getByRole('button',{name:'Play observed frames',exact:true}).click();
   assert.equal(await page.evaluate(()=>exploration.audit().playing),false);
   assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
   reports.push({name,initial,viewCount:views.length,externalRequests:external.length,errors,screenshots:output});
   await context.close();
  }
  fs.writeFileSync(path.join(output,'browser-report.json'),JSON.stringify(reports,null,2));
  console.log(JSON.stringify({passed:reports.length,reports},null,2));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
