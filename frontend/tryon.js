import { api, json, esc, money, imagePath } from './api.js';
import { icon } from './icons.js';
import { LiveCamera } from './camera.js';

/** @param {HTMLElement} root @param {import('./api.js').Product[]} catalog @param {string|null} preferred @param {(message:string)=>void} toast */
export function mountTryOn(root, catalog, preferred, toast) {
  const products = catalog.filter(p => p.try_on);
  if (!products.length) {
    root.innerHTML = '<div class="empty-state"><h1>Chưa có sản phẩm hỗ trợ thử phối.</h1><a href="#/shop" class="button primary">Khám phá cửa hàng</a></div>';
    return () => {};
  }
  const lifecycle = new AbortController();
  const signal = lifecycle.signal;
  let disposed = false;
  let busy = true;
  let openingCamera = false;
  /** @type {ImageBitmap|HTMLImageElement|HTMLCanvasElement|null} */
  let photo = null;
  /** @type {HTMLImageElement|null} */
  let overlay = null;
  /** @type {string|null} */
  let sessionId = null;
  let selected = products.find(p => p.id === preferred) || products[0];
  /** @type {'user'|'environment'} */
  let facing = 'user';
  let mirrored = true;
  let x = 50, y = 58, scale = 85, angle = 0;
  let dragging = false;
  /** @type {{x:number,y:number,baseX:number,baseY:number}|null} */
  let pointerStart = null;

  root.innerHTML = '<div class="page-intro tryon-intro"><p class="eyebrow">PHÒNG THỬ ĐỒ REALTIME</p><h1>Bật camera.<br><em>Thử một phong cách mới.</em></h1><p>Chọn món đồ và xem lớp phối trực tiếp qua camera của bạn.</p></div>' +
    '<div class="tryon-layout"><aside class="tryon-products surface"><div class="panel-title"><h2>Chọn món đồ</h2><span>'+products.length+' lựa chọn</span></div><label class="field"><span class="sr-only">Lọc loại sản phẩm thử đồ</span><select id="tryon-category"><option value="">Tất cả sản phẩm</option><option value="top">Áo</option><option value="dress">Váy & đầm</option><option value="glasses">Kính mắt</option><option value="watch">Đồng hồ</option></select></label><div id="tryon-product-list" class="tryon-product-list"></div></aside>' +
    '<section class="tryon-workspace"><div class="workspace-top"><span>'+icon('camera')+' Gương camera</span><span id="camera-badge" class="demo-label">CAMERA ĐANG TẮT</span></div><video id="tryon-video" muted playsinline hidden aria-hidden="true"></video><div class="canvas-wrap"><canvas id="tryon-canvas" width="800" height="900" aria-label="Gương camera có lớp phối đồ minh họa. Dùng thanh điều chỉnh để thay đổi vị trí." tabindex="0"></canvas><div id="photo-empty" class="photo-empty"><span>'+icon('camera')+'</span><h2>Gặp bạn trong gương.</h2><p>Bật camera để xem lớp phối đồ trực tiếp.<br>Video chỉ xử lý trên thiết bị, không tải lên máy chủ.</p><button id="start-camera" class="button primary" data-try-action="camera-start">'+icon('camera')+' Bật camera</button><label class="text-button upload-label" for="tryon-photo">Hoặc chọn một ảnh có sẵn</label></div></div><input class="sr-only" id="tryon-photo" type="file" accept="image/jpeg,image/png,image/webp">' +
    '<div class="camera-toolbar"><button id="toggle-camera" class="button secondary" data-try-action="camera-toggle">'+icon('camera')+' Bật camera</button><button id="switch-camera" class="button secondary" data-try-action="camera-switch" disabled>'+icon('refresh')+' Đổi camera</button><label class="mirror-toggle"><input id="camera-mirror" type="checkbox" checked> Lật gương</label></div><p id="camera-status" class="camera-status" role="status">Camera chỉ bật khi bạn chọn và cấp quyền.</p>' +
    '<div id="camera-secure-notice" class="camera-secure-notice" hidden><strong>Camera cần địa chỉ HTTPS hoặc localhost.</strong><p>Hãy mở liên kết HTTPS Tailscale được cung cấp cho demo. Nếu đang dùng SSH chuyển cổng, mở cửa hàng tại localhost trên máy của bạn.</p></div><div class="workspace-bottom"><span>'+icon('lock')+' Không ghi âm, không gửi video</span><label for="tryon-photo" class="small-link">Chọn ảnh thay thế</label></div><p id="tryon-error" class="form-error" role="alert"></p></section>' +
    '<aside class="tryon-settings surface"><p class="eyebrow">ĐANG THỬ PHỐI</p><h2 id="tryon-selected-name"></h2><p id="tryon-selected-price" class="purple"></p><div class="tryon-controls">'+[
      ['x','Vị trí ngang',0,100,50],['y','Vị trí dọc',0,100,58],['scale','Kích thước',15,160,85],['angle','Góc xoay',-180,180,0],
    ].map(([id,label,min,max,value])=>'<label class="range-field" for="tryon-'+id+'"><span>'+label+'<output id="output-'+id+'">'+value+(id==='angle'?'°':'%')+'</output></span><input id="tryon-'+id+'" type="range" min="'+min+'" max="'+max+'" value="'+value+'"></label>').join('')+'</div><button class="button secondary full" data-try-action="reset">'+icon('refresh')+' Đặt lại vị trí</button><button class="button primary full" id="download-tryon" data-try-action="download" disabled>'+icon('camera')+' Chụp ảnh phối đồ</button><a class="button ghost full" id="tryon-view-product" href="#/shop">Xem sản phẩm '+icon('arrow')+'</a><button class="delete-photo" data-try-action="delete">'+icon('trash')+' Tắt camera & xóa phiên thử</button><div class="tryon-disclaimer">'+icon('info')+'<p>Video và lớp phối cập nhật trực tiếp. Vị trí được chỉnh tay, chưa tự bám theo cơ thể. Lớp ghép là hình minh họa, không xác định size hoặc độ vừa vặn thực tế.</p></div></aside></div>' +
    '<div class="tryon-how"><span><b>1</b> Bật camera</span>'+icon('chevron')+'<span><b>2</b> Chọn món đồ</span>'+icon('chevron')+'<span><b>3</b> Chỉnh vị trí & chụp ảnh</span></div>';

  const canvas = root.querySelector('#tryon-canvas');
  const context = canvas.getContext('2d');
  const video = root.querySelector('#tryon-video');
  const error = root.querySelector('#tryon-error');
  const camera = new LiveCamera(video, draw, () => {
    if (disposed) return;
    updateUI();
    error.textContent = 'Camera đã ngắt kết nối. Kiểm tra thiết bị rồi chọn Bật camera lại.';
  });

  function hasSource() { return camera.active || photo !== null; }
  function updateUI() {
    if (disposed) return;
    root.querySelector('#photo-empty').hidden = hasSource();
    root.querySelector('#download-tryon').disabled = busy || !hasSource();
    root.querySelector('#tryon-photo').disabled = busy;
    root.querySelector('#start-camera').disabled = busy;
    const toggle = root.querySelector('#toggle-camera');
    toggle.disabled = busy;
    toggle.innerHTML = icon('camera') + (openingCamera ? ' Đang mở camera…' : camera.active ? ' Tắt camera' : ' Bật camera');
    const flip = root.querySelector('#switch-camera');
    flip.disabled = busy || !camera.active || camera.deviceCount < 2;
    flip.title = camera.deviceCount < 2 ? 'Cần ít nhất hai camera để chuyển đổi' : 'Chuyển camera trước/sau';
    root.querySelector('[data-try-action="delete"]').disabled = busy;
    root.querySelectorAll('[data-try-product]').forEach(button => { button.disabled = busy; });
    root.querySelector('#camera-mirror').checked = mirrored;
    const badge = root.querySelector('#camera-badge');
    badge.textContent = camera.active ? '● TRỰC TIẾP · DEMO' : photo ? 'ẢNH TĨNH · DEMO' : 'CAMERA ĐANG TẮT';
    badge.classList.toggle('camera-live', camera.active);
    root.querySelector('#camera-status').textContent = openingCamera ? 'Đang chờ quyền camera từ trình duyệt…' :
      camera.active ? 'Camera đang chạy. Di chuyển để xem trực tiếp; kéo lớp phối hoặc dùng thanh điều chỉnh.' :
      photo ? 'Camera đang tắt. Bạn đang xem ảnh tĩnh; bật lại camera để tiếp tục realtime.' :
      'Camera chỉ bật khi bạn chọn và cấp quyền.';
    root.querySelector('#camera-secure-notice').hidden = globalThis.isSecureContext;
  }
  function renderList() {
    const filter = root.querySelector('#tryon-category').value;
    root.querySelector('#tryon-product-list').innerHTML = products.filter(p=>!filter||p.try_on===filter).map(p=>'<button class="tryon-product '+(p.id===selected.id?'selected':'')+'" data-try-product="'+esc(p.id)+'" aria-pressed="'+(p.id===selected.id)+'" '+(busy?'disabled':'')+'><img src="'+imagePath(p.image)+'" alt="" width="62" height="76"><span><strong>'+esc(p.name)+'</strong><small>'+money(p.price)+'</small></span><span class="selection-dot">'+(p.id===selected.id?icon('check'):'')+'</span></button>').join('');
  }
  function syncControls() {
    for (const [id,value] of Object.entries({x,y,scale,angle})) {
      root.querySelector('#tryon-'+id).value=String(value);
      root.querySelector('#output-'+id).value=Math.round(value)+(id==='angle'?'°':'%');
    }
  }
  function draw() {
    if (disposed) return;
    context.fillStyle='#eee8f1';
    context.fillRect(0,0,800,900);
    const source = camera.active ? video : photo;
    const sourceWidth = camera.active ? video.videoWidth : photo?.width;
    const sourceHeight = camera.active ? video.videoHeight : photo?.height;
    if (!source || !sourceWidth || !sourceHeight) return;
    const ratio=Math.min(800/sourceWidth,900/sourceHeight);
    const width=sourceWidth*ratio, height=sourceHeight*ratio;
    context.save();
    if (mirrored) { context.translate(800,0); context.scale(-1,1); }
    context.drawImage(source,(800-width)/2,(900-height)/2,width,height);
    context.restore();
    if (overlay) {
      const overlayWidth=800*scale/100;
      context.save();
      context.translate(800*x/100,900*y/100);
      context.rotate(angle*Math.PI/180);
      context.drawImage(overlay,-overlayWidth/2,-overlayWidth/2,overlayWidth,overlayWidth);
      context.restore();
    }
  }
  function clearPhoto() {
    if (photo instanceof ImageBitmap) photo.close();
    photo=null;
  }
  function resetPosition() {
    x=50;angle=0;
    if (selected.try_on==='glasses') { y=40;scale=48; }
    else if (selected.try_on==='watch') { x=35;y=83;scale=25; }
    else if (selected.try_on==='dress') { y=76;scale=105; }
    else { y=64;scale=85; }
    syncControls();draw();
  }
  async function endSession() {
    if (!sessionId) return;
    const id=sessionId;
    await api('/try-on/'+id,{method:'DELETE',keepalive:true});
    if (sessionId===id) sessionId=null;
  }
  async function replaceSession() {
    await endSession();
    if (disposed || !hasSource()) return;
    const session=await api('/try-on',json('POST',{product_id:selected.id}));
    if (disposed) { await api('/try-on/'+session.id,{method:'DELETE',keepalive:true});return; }
    sessionId=session.id;
  }
  async function choose(product) {
    const asset=product.try_on==='glasses'?'glasses':product.try_on==='watch'?'watch':product.try_on==='dress'?'dress':product.category==='outerwear'?'jacket':'shirt';
    const image=new Image();
    image.src='/static/assets/'+asset+'.svg';
    await image.decode();
    if (disposed) return;
    selected=product;overlay=image;
    root.querySelector('#tryon-selected-name').textContent=product.name;
    root.querySelector('#tryon-selected-price').textContent=money(product.price);
    root.querySelector('#tryon-view-product').href='#/product/'+encodeURIComponent(product.id);
    resetPosition();renderList();
    if (hasSource()) await replaceSession();
  }
  async function startCamera() {
    openingCamera=true;updateUI();
    try {
      if (!await camera.start(facing) || disposed) return;
      clearPhoto();
      mirrored=facing==='user';
      updateUI();draw();
      await replaceSession();
    } finally {
      openingCamera=false;
    }
  }
  function freezeCamera() {
    if (video.videoWidth && video.videoHeight) {
      const frame=document.createElement('canvas');
      frame.width=video.videoWidth;frame.height=video.videoHeight;
      frame.getContext('2d').drawImage(video,0,0);
      clearPhoto();photo=frame;
    }
    camera.stop();
    updateUI();draw();
  }
  function cleanup() {
    if (disposed) return;
    disposed=true;lifecycle.abort();camera.stop();clearPhoto();
    endSession().catch(failure=>toast('Chưa xóa được phiên thử: '+failure.message));
  }

  root.querySelector('#tryon-photo').addEventListener('change',async event=>{
    const file=event.target.files?.[0];
    if (!file || busy) return;
    error.textContent='';
    if (!['image/jpeg','image/png','image/webp'].includes(file.type)) {error.textContent='Chọn ảnh JPG, PNG hoặc WebP.';return;}
    if (file.size>8*1024*1024) {error.textContent='Ảnh phải nhỏ hơn 8 MB.';return;}
    busy=true;updateUI();
    try {
      const bitmap=await createImageBitmap(file);
      if (bitmap.width*bitmap.height>24000000) {bitmap.close();throw new Error('Ảnh quá lớn. Hãy chọn ảnh dưới 24 megapixel.');}
      if (disposed) {bitmap.close();return;}
      camera.stop();clearPhoto();photo=bitmap;mirrored=false;
      draw();await replaceSession();
    } catch (failure) {if(!disposed)error.textContent='Chưa mở được ảnh: '+failure.message;}
    finally {busy=false;updateUI();event.target.value='';}
  },{signal});

  root.addEventListener('click',async event=>{
    const productButton=event.target.closest('[data-try-product]');
    const action=event.target.closest('[data-try-action]')?.dataset.tryAction;
    if (busy || (!productButton && !action)) return;
    if (action==='reset') {resetPosition();return;}
    if (action==='download') {
      if (!hasSource()) return;
      draw();
      canvas.toBlob(blob=>{
        if (!blob) {error.textContent='Chưa lưu được ảnh. Hãy thử chụp lại.';return;}
        const url=URL.createObjectURL(blob);
        const link=document.createElement('a');link.href=url;link.download='may-camera-phoi-do-demo.png';link.click();
        setTimeout(()=>URL.revokeObjectURL(url),1000);
        toast('Đã chụp khung hình phối đồ');
      },'image/png');
      return;
    }
    busy=true;error.textContent='';updateUI();
    try {
      if (productButton) await choose(products.find(p=>p.id===productButton.dataset.tryProduct));
      else if (action==='camera-start' || action==='camera-toggle') {
        if (camera.active) freezeCamera();
        else await startCamera();
      } else if (action==='camera-switch') {
        facing=facing==='user'?'environment':'user';
        await startCamera();
      } else if (action==='delete') {
        camera.stop();clearPhoto();draw();updateUI();
        await endSession();
        toast('Đã tắt camera và xóa phiên thử');
      }
    } catch (failure) {if(!disposed)error.textContent=failure.message;}
    finally {busy=false;updateUI();}
  },{signal});

  root.querySelector('#tryon-category').addEventListener('change',renderList,{signal});
  root.querySelector('#camera-mirror').addEventListener('change',event=>{mirrored=event.target.checked;draw();},{signal});
  root.querySelector('.tryon-controls').addEventListener('input',()=>{
    x=Number(root.querySelector('#tryon-x').value);
    y=Number(root.querySelector('#tryon-y').value);
    scale=Number(root.querySelector('#tryon-scale').value);
    angle=Number(root.querySelector('#tryon-angle').value);
    syncControls();draw();
  },{signal});
  canvas.addEventListener('pointerdown',event=>{
    if (!hasSource()) return;
    dragging=true;pointerStart={x:event.clientX,y:event.clientY,baseX:x,baseY:y};canvas.setPointerCapture(event.pointerId);
  },{signal});
  canvas.addEventListener('pointermove',event=>{
    if (!dragging || !pointerStart) return;
    const rect=canvas.getBoundingClientRect();
    x=Math.max(0,Math.min(100,pointerStart.baseX+(event.clientX-pointerStart.x)/rect.width*100));
    y=Math.max(0,Math.min(100,pointerStart.baseY+(event.clientY-pointerStart.y)/rect.height*100));
    syncControls();draw();
  },{signal});
  canvas.addEventListener('pointerup',()=>{dragging=false;},{signal});
  canvas.addEventListener('pointercancel',()=>{dragging=false;},{signal});
  window.addEventListener('pagehide',cleanup,{signal});
  renderList();updateUI();draw();
  choose(selected).catch(failure=>{if(!disposed)error.textContent=failure.message;}).finally(()=>{busy=false;updateUI();});
  return cleanup;
}
