const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {randomUUID} = require('node:crypto');
const root = path.resolve(__dirname, '..');
const reports = path.join(root, 'reports');
fs.mkdirSync(reports, {recursive:true});
fs.mkdirSync(path.join(root,'.test-work'),{recursive:true});
const checks=[];
let server,browser,page;
async function check(name, fn) {await fn();checks.push(name);console.log('PASS '+name);}
async function readable(page) {
  const failures=await page.evaluate(()=>{
    const rgb=s=>(s.match(/[\d.]+/g)||[]).map(Number);
    const blend=(a,b)=>a.slice(0,3).map((v,i)=>v*(a[3]??1)+b[i]*(1-(a[3]??1)));
    const lum=a=>a.slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
    return [...document.querySelectorAll('body *')].filter(n=>n.getClientRects().length&&!n.closest('[aria-hidden="true"], [disabled]')&&[...n.childNodes].some(c=>c.nodeType===3&&c.textContent.trim())).flatMap(n=>{
      let chain=[];for(let p=n;p;p=p.parentElement)chain.unshift(p);
      const bg=chain.reduce((b,p)=>blend(rgb(getComputedStyle(p).backgroundColor),b),[255,255,255]);
      const s=getComputedStyle(n),[hi,lo]=[lum(blend(rgb(s.color),bg)),lum(bg)].sort((a,b)=>b-a);
      const minimum=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&parseInt(s.fontWeight)>=700)?3:4.5;
      return (hi+.05)/(lo+.05)+.01>=minimum?[]:[n.tagName+'.'+n.className+': '+n.textContent.trim().slice(0,35)];
    });
  });
  assert.deepEqual(failures,[],'Text contrast');
}
(async()=>{
  server=spawn(path.join(root,'../.venv/Scripts/python.exe'),['-u','-m','repair_shop.tests.browser_server','--db',path.join(root,'.test-work',randomUUID()+'.db')],{cwd:path.join(root,'..'),windowsHide:true,stdio:['ignore','pipe','pipe']});
  let diagnostics='';server.stderr.on('data',d=>diagnostics=(diagnostics+d).slice(-2000));
  const base=await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('Startup timeout: '+diagnostics)),15000);
    server.stdout.on('data',d=>{const m=String(d).match(/READY (http:\/\/127\.0\.0\.1:\d+)/);if(m){clearTimeout(timer);resolve(m[1]);}});
    server.on('error',reject);server.on('exit',code=>{if(code){clearTimeout(timer);reject(Error(diagnostics));}});
  });
  browser=await chromium.launch({channel:'msedge',headless:true});
  page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[],external=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith(base))external.push(r.url());});
  await page.goto(base);
  await check('Empty local dashboard and keyboard skip link',async()=>{
    await page.getByRole('heading',{name:'A clear view of your workshop.'}).waitFor();
    await page.locator('.skip-link').focus();await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(()=>document.activeElement.id),'main-content');
    await readable(page);
    await page.screenshot({path:path.join(reports,'dashboard-empty.png'),fullPage:true});
  });
  await check('Explicit currency, USD and CNY displays',async()=>{
    await page.goto(base+'/currency');
    assert.equal(await page.locator('input[name=currency]:checked').count(),0);
    await page.getByLabel('US dollar (USD)').check();await page.getByRole('button',{name:'Save currency'}).click();
    await page.getByText('USD 0.00',{exact:true}).first().waitFor();
    await page.goto(base+'/currency');await page.getByLabel('Chinese yuan (CNY)').check();
    await page.getByRole('button',{name:'Save currency'}).click();
    await page.getByText('CNY 0.00',{exact:true}).first().waitFor();
  });
  await check('Customer form errors retain values and Unicode names',async()=>{
    await page.goto(base+'/customers/new');
    await page.getByLabel('Full name').fill('Alex Chen 陈明');await page.getByLabel('Phone number').fill('bad');
    await page.getByRole('button',{name:'Save customer'}).click();
    await page.locator('#phone-error').waitFor();
    assert.equal(await page.getByLabel('Full name').inputValue(),'Alex Chen 陈明');
    await page.getByLabel('Phone number').fill('+86 (138) 0013-8000');await page.getByRole('button',{name:'Save customer'}).click();
    await page.getByRole('heading',{name:'Alex Chen 陈明',exact:true}).waitFor();
  });
  await check('Technician creation using keyboard',async()=>{
    await page.goto(base+'/technicians/new');await page.getByLabel('Full name').focus();
    await page.keyboard.type('Jordan Lee');await page.keyboard.press('Tab');await page.keyboard.type('13900139000');
    await page.getByRole('button',{name:'Save technician'}).focus();await page.keyboard.press('Enter');
    await page.getByText('Jordan Lee',{exact:true}).first().waitFor();
  });
  let orderUrl;
  await check('Create order, exact amounts, escaped text and currency lock',async()=>{
    await page.goto(base+'/orders/new');
    await page.getByLabel(/^Customer/).selectOption({label:'Alex Chen 陈明 · +8613800138000'});
    await page.getByLabel('Technician').selectOption({label:'Jordan Lee'});
    await page.getByLabel('Device type').fill('Laptop');await page.getByLabel('Brand / model').fill('Dell XPS 13');
    await page.getByLabel('Problem description').fill('Device will not start. <script>window.injection=true</script>');
    await page.getByLabel('Repair price (CNY)').fill('150.00');
    const token=await page.locator('input[name=request_token]').inputValue();
    let requests=0;
    await page.route('**/orders/new',async route=>{
      if(route.request().method()!=='POST')return route.continue();
      assert.ok(route.request().postData().includes(token));
      requests++;
      if(requests===1)return route.abort('failed');
      return route.continue();
    });
    await page.getByRole('button',{name:'Create order',exact:true}).click();
    await page.getByRole('alert').filter({hasText:'Your entries are still here'}).waitFor();
    assert.equal(await page.getByLabel('Brand / model').inputValue(),'Dell XPS 13');
    assert.equal(await page.locator('input[name=request_token]').inputValue(),token);
    await page.getByRole('button',{name:'Create order',exact:true}).click();orderUrl=page.url();
    await page.getByRole('heading',{name:/R-00001/}).waitFor();
    orderUrl=page.url();assert.equal(requests,2);await page.unroute('**/orders/new');
    assert.equal(await page.evaluate(()=>window.injection),undefined);
    await page.goto(base+'/currency');await page.getByText('Currency is locked while repair orders exist.',{exact:true}).waitFor();
    await page.goto(orderUrl);
  });
  await check('Status workflow and partial payment',async()=>{
    await page.getByRole('button',{name:'Start repair',exact:true}).click();
    await page.getByRole('link',{name:'Add payment',exact:true}).click();
    await page.getByLabel('Amount (CNY)').fill('50.00');await page.getByRole('button',{name:'Save payment'}).click();
    await page.getByText('CNY 100.00',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Mark ready',exact:true}).click();
    assert.equal(await page.getByRole('link',{name:'Deliver device',exact:true}).count(),0);
    await page.screenshot({path:path.join(reports,'order-desktop.png'),fullPage:true});
    await readable(page);
  });
  await check('Delete-payment confirmation and cancel preserve balances',async()=>{
    await page.getByRole('link',{name:'Delete payment',exact:true}).first().click();
    await page.getByRole('heading',{name:'Delete payment?'}).waitFor();
    await page.getByRole('link',{name:'Cancel',exact:true}).click();
    await page.getByText('CNY 100.00',{exact:true}).waitFor();
  });
  await check('Full settlement and explicit delivery confirmation',async()=>{
    await page.getByRole('link',{name:'Add payment',exact:true}).click();await page.getByLabel('Amount (CNY)').fill('100');
    await page.getByRole('button',{name:'Save payment'}).click();
    await page.getByRole('link',{name:'Deliver device',exact:true}).click();
    await page.getByRole('heading',{name:'Deliver device?'}).waitFor();
    await page.getByRole('link',{name:'Cancel',exact:true}).click();
    await page.getByRole('link',{name:'Deliver device',exact:true}).click();
    await page.getByRole('button',{name:'Confirm delivery'}).click();
    await page.getByText('This order is delivered and read-only.',{exact:true}).waitFor();
    await page.reload();assert.equal(await page.getByRole('link',{name:'Add payment',exact:true}).count(),0);
  });
  await check('Search and clear filters',async()=>{
    await page.goto(base+'/orders');await page.getByLabel('Search orders').fill('missing');await page.getByRole('button',{name:'Apply filters'}).click();
    await page.getByRole('heading',{name:'No matching orders'}).waitFor();await page.getByRole('link',{name:'Clear filters'}).click();
    await page.getByRole('link',{name:'R-00001',exact:true}).waitFor();
  });
  await check('Responsive English pages and text contrast at 360, 768, 1440 pixels',async()=>{
    for(const width of [360,768,1440]) {
      await page.setViewportSize({width,height:950});
      for(const [name,url] of [['dashboard',base],['orders',base+'/orders'],['customers',base+'/customers'],['technicians',base+'/technicians'],['order',orderUrl],['new-order',base+'/orders/new'],['currency',base+'/currency']]) {
        await page.goto(url);await readable(page);
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),name+' overflow at '+width);
        await page.screenshot({path:path.join(reports,`${name}-${width}.png`),fullPage:true});
      }
    }
  });
  await check('No external requests or script errors',async()=>{assert.deepEqual(external,[]);assert.deepEqual(errors,[]);});
  fs.writeFileSync(path.join(reports,'browser-results.json'),JSON.stringify({passed:checks.length,checks,widths:[360,768,1440],testDataOnly:true},null,2));
  console.log(`${checks.length} browser checks passed.`);
})().catch(async e=>{console.error(e.stack);if(page){await page.screenshot({path:path.join(reports,'browser-failure.png'),fullPage:true});console.error((await page.locator('body').innerText()).slice(0,1800));}process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)server.kill();});
