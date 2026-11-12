/* Adaptation of PTIT Ami from this repository for the FastAPI fashion store. */
(() => {
  let model = null;
  let mouth = 0;
  let visible = true;
  const loading = document.querySelector('#ami-loading');
  function announce(state, message) {
    window.parent.postMessage({type:'may-ami-status',state,message},location.origin);
  }
  async function start() {
    const app = new PIXI.Application({
      view:document.querySelector('#ami-canvas'),width:innerWidth,height:innerHeight,
      backgroundAlpha:0,antialias:true,autoDensity:true,resolution:Math.min(devicePixelRatio,2),
    });
    PIXI.live2d.Live2DModel.registerTicker(PIXI.Ticker);
    model = await PIXI.live2d.Live2DModel.from('/ami-assets/model/PTIT_Ami/ptit_sdk.model3.json',{autoInteract:false});
    app.stage.addChild(model);
    const naturalWidth = model.width;
    const naturalHeight = model.height;
    model.anchor.set(0.5,0.04);
    function resize() {
      app.renderer.resize(innerWidth,innerHeight);
      model.scale.set(Math.min(innerWidth/naturalWidth,innerHeight/naturalHeight)*1.65);
      model.position.set(innerWidth/2,innerHeight*0.02);
    }
    resize();
    window.addEventListener('resize',resize);
    model.internalModel.on('beforeModelUpdate',() => model.internalModel.coreModel.setParameterValueById('ParamMouthOpenY',mouth));
    await model.expression('Happy');
    loading.hidden = true;
    announce('ready','Ami đã sẵn sàng');
    window.addEventListener('message',async event => {
      if(event.origin!==location.origin||event.source!==window.parent||!event.data||typeof event.data!=='object')return;
      const message=event.data;
      if(message.type==='may-ami-mouth'&&typeof message.value==='number'&&Number.isFinite(message.value))mouth=Math.max(0,Math.min(1,message.value));
      else if(message.type==='may-ami-visible'&&typeof message.visible==='boolean'){
        visible=message.visible;model.autoUpdate=visible;
        if(visible)app.start();else app.stop();
      }else if(message.type==='may-ami-expression'&&['Happy','Think_1','Default'].includes(message.name)){
        try{await model.expression(message.name);}catch(error){announce('error','Không tải được biểu cảm Ami.');}
      }
    });
    if(!visible){model.autoUpdate=false;app.stop();}
    window.addEventListener('pagehide',()=>{model.destroy();app.destroy(true);},{once:true});
  }
  start().catch(error=>{
    loading.textContent='Chưa tải được nhân vật Ami. Bạn vẫn có thể trò chuyện.';
    announce('error',loading.textContent);
  });
})();
