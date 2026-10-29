/* Append to a compiled midterm example to verify native SVG motion in a real browser. */
(async function () {
  const viewer = window.exploration;
  const root = viewer.element.shadowRoot;
  const results = [];
  const pause = duration => new Promise(resolve => setTimeout(resolve, duration));
  const nextFrame = () => new Promise(resolve => requestAnimationFrame(resolve));
  const settleMotion = async () => { await Promise.allSettled(root.getAnimations({subtree:true}).map(animation => animation.finished)); await nextFrame(); await nextFrame(); };
  const requireCondition = (condition, message) => { if (!condition) throw new Error(message); };
  const check = async (name, operation) => {
    try { await operation(); results.push({name, passed: true}); }
    catch (error) { results.push({name, passed: false, error: error.message}); }
  };
  const mark = () => root.querySelector('.plot [data-observation-key]');
  const position = node => {
    const local = node.tagName.toLowerCase() === 'circle' ? new DOMPoint(+node.getAttribute('cx'), +node.getAttribute('cy')) : new DOMPoint(0, 0);
    return local.matrixTransform(node.getScreenCTM()).matrixTransform(node.ownerSVGElement.getScreenCTM().inverse());
  };
  const distance = (left, right) => Math.hypot(left.x - right.x, left.y - right.y);
  await pause(100);
  await check('Native observed-frame motion reaches the exact measured position', async () => {
    viewer.seek(2006);
    await settleMotion();
    const previous = position(mark());
    viewer.seek(2010);
    const current = mark();
    requireCondition(current.getAnimations().length > 0, 'No native mark animation started');
    const beginning = position(current);
    requireCondition(distance(previous, beginning) < 2, 'A frame transition jumped before moving');
    requireCondition(viewer.getRows().every(row => row.year === 2010), 'Rows must contain only observed 2010 measurements during motion');
    const animation = current.getAnimations()[0];
    animation.pause();
    await animation.ready;
    animation.currentTime = animation.effect.getTiming().duration / 2;
    const middle = position(current);
    animation.play();
    await settleMotion();
    const ending = position(current);
    requireCondition(distance(previous, ending) > 1, 'Fixture observation did not change position');
    requireCondition(distance(middle, ending) < distance(previous, ending), 'Animation did not approach the measured destination: '+JSON.stringify({previous,beginning,middle,ending,connected:current.isConnected,transform:getComputedStyle(current).transform,animationCount:current.getAnimations().length}));
    requireCondition(current.getAnimations().length === 0, 'Native motion did not finish');
    const geometry = current.getAttribute('transform')?.match(/translate\(([-.\d]+)[, ]+([-.\d]+)\)/);
    const exact = geometry ? {x: +geometry[1], y: +geometry[2]} : {x: +current.getAttribute('cx'), y: +current.getAttribute('cy')};
    const measuredPosition = new DOMPoint(exact.x, exact.y).matrixTransform(current.parentElement.getScreenCTM()).matrixTransform(current.ownerSVGElement.getScreenCTM().inverse());
    requireCondition(distance(ending, measuredPosition) < .1, 'Final visible position differs from the observation');
  });
  await check('Interrupted motion continues from its visible position', async () => {
    viewer.seek(2006);
    await settleMotion();
    viewer.seek(2010);
    const interrupted = mark().getAnimations()[0];
    interrupted.pause();
    await interrupted.ready;
    interrupted.currentTime = interrupted.effect.getTiming().duration / 2;
    const visible = position(mark());
    viewer.seek(2014);
    requireCondition(distance(visible, position(mark())) < 2, 'Interrupted animation jumped to a previous endpoint');
    await settleMotion();
    requireCondition(!viewer.audit().animating, 'Interrupted motion was not released');
  });
  await check('Focused history has one observed cursor and exact parent restoration', async () => {
    const entity = viewer.getRows()[0].state;
    viewer.select([entity]);
    const parent = JSON.stringify(viewer.getState());
    requireCondition(viewer.focusEntity(entity), 'Entity history could not be opened');
    requireCondition(viewer.getRows().length === 5, 'History should retain five observed elections');
    requireCondition(root.querySelectorAll('[data-time-cursor]').length === 1, 'History must show one time cursor');
    viewer.seek(2006);
    await settleMotion();
    viewer.seek(2010);
    requireCondition(root.querySelector('[data-time-cursor]').getAnimations().length > 0, 'History cursor did not animate');
    viewer.back();
    requireCondition(JSON.stringify(viewer.getState()) === parent, 'Returning changed the parent comparison');
  });
  await check('Inspection closes cleanly and the drawing does not overflow', async () => {
    const close = root.querySelector('[aria-label="Close data sheet"]');
    requireCondition(close && !root.querySelector('.sidebar').hidden, 'Inspection sheet did not open');
    close.click();
    requireCondition(root.querySelector('.sidebar').hidden, 'Inspection sheet remained open');
    requireCondition(viewer.getState().selected.length === 0, 'Closing inspection left unrelated observations faded');
    requireCondition(!viewer.audit().overflow, 'The drawing exceeds its available width');
  });
  await check('Every view renders and exports its exact displayed observations', async () => {
    for (const view of viewer.getDocument().views) {
      viewer.setState({view: view.id, filters: {}, search: '', selected: [], brush: null});
      requireCondition(viewer.audit().errors === 0, `${view.id} reported a rendering error`);
      requireCondition(!viewer.audit().overflow, `${view.id} exceeded the drawing width`);
      if (view.type !== 'table') requireCondition(root.querySelector('.plot svg'), `${view.id} has no drawing`);
      requireCondition(viewer.exportCSV().split('\r\n').length === viewer.getRows().length + 1, `${view.id} export disagrees with its displayed observations`);
    }
  });
  const output = document.createElement('pre');
  output.id = 'browser-verification';
  output.dataset.result = results.every(result => result.passed) ? 'passed' : 'failed';
  output.textContent = JSON.stringify(results, null, 2);
  document.body.prepend(output);
})().catch(error => {
  const output = document.createElement('pre');
  output.id = 'browser-verification';
  output.dataset.result = 'failed';
  output.textContent = error.stack;
  document.body.prepend(output);
});
