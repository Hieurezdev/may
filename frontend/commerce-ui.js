import { api, json, esc, money } from './api.js';

const returnNames = {requested:'Chờ xét duyệt',approved:'Đã duyệt · chờ nhận hàng',rejected:'Đã từ chối',inspected:'Đã kiểm tra hàng',refund_pending:'Đang hoàn tiền',completed:'Đã hoàn tất'};
const fallbackNames = {opt_out:'Bạn đang xem gợi ý phổ biến. Bật cá nhân hóa nếu muốn dùng lịch sử mua hàng.',missing_model:'Mây chưa có đủ dữ liệu để cá nhân hóa; bạn đang xem các lựa chọn phổ biến.',cold_start:'Mua sắm thêm một chút để mây hiểu gu của bạn. Hiện tại là gợi ý phổ biến.',noise:'Chưa tìm được nhóm mua sắm phù hợp; bạn đang xem các lựa chọn phổ biến.',empty_segment:'Nhóm của bạn chưa có sản phẩm phù hợp còn hàng. Mây gợi ý các lựa chọn phổ biến.'};
const heading = (title,description) => '<div class="page-intro"><p class="eyebrow">MÂY · ĐỒNG HÀNH CÙNG BẠN</p><h1>'+esc(title)+'</h1><p>'+esc(description)+'</p></div>';
const reportButton = (label,action,id,extra='') => '<button type="button" class="button secondary" data-report="'+action+'" data-id="'+esc(id)+'" '+extra+'>'+esc(label)+'</button>';

export function orderExtras(order) {
  const cancelable = ['pending_payment','confirmed','paid','processing','payment_failed','expired'].includes(order.status);
  return '<div class="order-tools">'+(cancelable?reportButton('Hủy đơn','cancel-order',order.id):'')+(order.status==='delivered'?reportButton('Yêu cầu đổi trả','return-order',order.id):'')+'</div>'+
    (order.shipment?'<p class="source-note">Vận chuyển: '+esc(order.shipment.provider)+' · Mã vận đơn <strong>'+esc(order.shipment.tracking_code)+'</strong> · '+(order.shipment.status==='delivered'?'Đã giao':'Đang giao')+'</p>':'')+
    (order.returns?.length?'<div class="return-summary">'+order.returns.map(r=>'<p><strong>Đổi trả:</strong> '+esc(returnNames[r.status]||r.status)+' · '+esc(r.reason)+(r.review_reason?'<br>'+esc(r.review_reason):'')+(r.refund_amount?'<br>Hoàn '+money(r.refund_amount)+' · '+esc(r.refund_status):'')+'</p>').join('')+'</div>':'');
}

/** Keep new flows on the existing store components and event lifecycle. */
export function commerceUI({modal,toast,refresh,getCustomer,getProducts,productGrid}) {
  function open(title,body) {
    modal.innerHTML='<div class="dialog-top"><h2 id="dialog-title">'+esc(title)+'</h2><button type="button" class="icon-button" data-action="close-modal" aria-label="Đóng">×</button></div>'+body;
    if(!modal.open)modal.showModal();
  }
  async function cancelOrder(id) {
    open('Hủy đơn hàng','<form id="cancel-order-form" data-id="'+esc(id)+'"><label class="field">Lý do hủy<textarea name="reason" minlength="5" maxlength="1000" required></textarea></label><p class="fine-print">Đơn đã thanh toán sẽ được tạo yêu cầu hoàn tiền; kết quả hoàn được cập nhật sau khi xác minh.</p><p class="form-error" role="alert"></p><button class="button primary" type="submit">Xác nhận hủy đơn</button></form>');
  }
  async function returnOrder(id) {
    const order=await api('/orders/'+encodeURIComponent(id));
    open('Đổi trả đơn hàng','<form id="return-order-form" data-id="'+esc(id)+'">'+order.items.map((l,i)=>'<label class="field">'+esc(l.name)+' · '+esc(l.color)+' / '+esc(l.size)+'<input type="number" name="line:'+esc(l.id)+'" min="0" max="'+l.quantity+'" value="'+(i===0?'1':'0')+'" required><small>Nhập 0 để không trả dòng hàng này.</small></label>').join('')+'<label class="field">Lý do<textarea name="reason" minlength="5" maxlength="1000" required></textarea></label><label class="field">Thông tin bổ sung hoặc liên kết bằng chứng<textarea name="evidence" maxlength="2000"></textarea></label><p class="fine-print">Yêu cầu trong 7 ngày kể từ lúc nhận hàng. Hàng được kiểm tra trước khi hoàn tiền.</p><p class="form-error" role="alert"></p><button class="button primary" type="submit">Gửi yêu cầu</button></form>');
  }
  function imageSearch() {
    open('Tìm món đồ từ ảnh','<form id="image-search-form"><label class="field">Chọn ảnh sản phẩm<input id="search-image-file" name="image" type="file" accept="image/jpeg,image/png,image/webp" required></label><label class="field">Mô tả thêm, nếu có<input name="query" maxlength="200" placeholder="Ví dụ: áo khoác màu be"></label><label class="payment-option"><input name="consent" type="checkbox" required><span>Tôi đồng ý gửi ảnh tới dịch vụ tìm kiếm. Ảnh không được lưu trên máy chủ.</span></label><p class="form-error" role="alert"></p><button class="button primary" type="submit">Tìm sản phẩm</button></form><div id="image-search-results" aria-live="polite"></div>');
  }
  async function recommendationsPage() {
    const [result,consent]=await Promise.all([api('/recommendations'),api('/me/recommendation-consent')]);
    const map=new Map(getProducts().map(p=>[p.id,p]));
    const products=result.product_ids.map(id=>map.get(id)).filter(Boolean);
    return heading('Một chút hợp gu.','Những món đồ còn hàng, phù hợp để bạn khám phá tiếp.')+'<section class="surface"><p>'+esc(result.mode==='dbscan-peers'?'Gợi ý dựa trên những khách hàng có thói quen mua sắm tương tự.':fallbackNames[result.fallback_reason]||'Gợi ý từ danh mục hiện tại.')+'</p>'+(getCustomer().registered?'<form id="recommendation-consent-form"><label class="payment-option"><input name="consent" type="checkbox" '+(consent.consent?'checked':'')+'><span>Cho phép dùng lịch sử mua hàng của tôi để cá nhân hóa gợi ý</span></label><p class="fine-print">Có thể tắt bất kỳ lúc nào. Khi tắt, hệ thống xóa liên kết phân nhóm của bạn.</p><button class="button secondary" type="submit">Lưu lựa chọn</button><p class="form-error" role="alert"></p></form>':'<p>Đăng nhập để quản lý lựa chọn cá nhân hóa.</p>')+'</section>'+productGrid(products);
  }
  async function addressesPage() {
    const addresses=await api('/addresses');
    return heading('Địa chỉ của bạn.','Lưu thông tin để điền nhanh khi đặt hàng.')+'<section class="surface">'+addresses.map(a=>'<p><strong>'+esc(a.recipient_name)+'</strong> · '+esc(a.phone)+'<br>'+esc(a.address)+' '+reportButton('Xóa','delete-address',a.id)+'</p>').join('')+'<form id="address-form"><label class="field">Người nhận<input name="recipient_name" minlength="2" maxlength="100" required></label><label class="field">Điện thoại<input name="phone" type="tel" pattern="0[35789][0-9]{8}" required></label><label class="field">Địa chỉ<textarea name="address" minlength="10" maxlength="500" required></textarea></label><button class="button primary" type="submit">Lưu địa chỉ</button><p class="form-error" role="alert"></p></form></section>';
  }
  async function staffPage() {
    const role=getCustomer().role;
    if(role==='merchant')return merchantPage();
    if(role==='support')return supportPage();
    if(role==='operator')return operatorPage();
    return heading('Khu vực vận hành','Tài khoản hiện tại không có quyền truy cập.');
  }
  async function merchantPage() {
    const [catalog,orders,inventory,returns]=await Promise.all([api('/admin/products'),api('/admin/orders'),api('/admin/inventory'),api('/admin/returns')]);
    const inventoryMap=new Map(inventory.map(i=>[i.variant_id,i]));
    const transitions={confirmed:['processing'],paid:['processing'],shipped:['delivered']};
    return heading('Chăm chút cửa hàng.','Quản lý danh mục, tồn kho và giao hàng.')+'<section id="fulfillment-section" class="surface"><h2>Đơn hàng</h2>'+orders.map(o=>'<article class="operation-row"><strong>'+esc(o.id)+'</strong><p>'+esc(o.recipient_name)+' · '+money(o.total)+' · '+esc(o.status)+'</p>'+(transitions[o.status]?'<form class="report-status-form" data-id="'+esc(o.id)+'"><select name="status" aria-label="Trạng thái đơn">'+transitions[o.status].map(s=>'<option value="'+s+'">'+(s==='processing'?'Chuẩn bị hàng':'Xác nhận đã giao và thu COD nếu có')+'</option>').join('')+'</select><button class="button secondary" type="submit">Cập nhật</button><p class="form-error" role="alert"></p></form>':'')+(o.status==='processing'?reportButton('Xuất kho và tạo vận đơn','ship',o.id):'')+'</article>').join('')+'</section><section id="return-inspection-section" class="surface"><h2>Nhận hàng trả</h2>'+returnCards(returns,'merchant')+'</section><section id="catalog-maintenance-section" class="surface"><h2>Danh mục và tồn kho thực tế</h2><div class="inventory-grid">'+catalog.map(p=>'<details><summary>'+esc(p.name)+(p.active===false?' · Ngừng bán':'')+'</summary><form class="report-product-form" data-id="'+esc(p.id)+'"><label class="field">Tên<input name="name" value="'+esc(p.name)+'" minlength="2" maxlength="200" required></label><label class="field">Giá VND<input name="price" type="number" min="0" max="100000000" value="'+p.price+'" required></label><label class="field">Hiển thị<select name="active"><option value="true">Đang bán</option><option value="false">Ngừng bán</option></select></label><label class="field">Lý do thay đổi<input name="reason" minlength="5" maxlength="500" required></label><button class="button secondary" type="submit">Lưu sản phẩm</button><p class="form-error" role="alert"></p></form>'+p.variants.map(v=>'<form class="report-stock-form" data-id="'+esc(v.id)+'"><label class="field">'+esc(v.color)+' / '+esc(v.size)+' · Đang giữ '+inventoryMap.get(v.id).reserved+' · Có thể bán '+v.stock+'<input name="stock" type="number" min="'+inventoryMap.get(v.id).reserved+'" max="100000" value="'+inventoryMap.get(v.id).on_hand+'" required></label><button class="button secondary" type="submit">Lưu tồn thực tế</button><p class="form-error" role="alert"></p></form>').join('')+'</details>').join('')+'</div></section>';
  }
  function returnCards(returns,role) {
    return returns.length?returns.map(r=>'<article class="operation-row"><strong>'+esc(r.id)+'</strong><p>Đơn '+esc(r.order_id)+' · '+esc(returnNames[r.status])+'</p><p>'+esc(r.reason)+'</p>'+r.lines.map(l=>'<small>Dòng '+esc(l.order_line_id)+' · SL '+l.quantity+'</small>').join('<br>')+(role==='support'&&r.status==='requested'?reportButton('Xét duyệt','review-return',r.id):'')+(role==='merchant'&&r.status==='approved'?reportButton('Ghi nhận kiểm tra hàng','inspect-return',r.id):'')+(role==='support'&&r.status==='inspected'?reportButton('Yêu cầu hoàn tiền','refund-return',r.id):'')+'</article>').join(''):'<p class="muted">Chưa có yêu cầu cần xử lý.</p>';
  }
  async function supportPage() {
    return heading('Hỗ trợ đổi trả.','Xét duyệt theo chính sách và theo dõi kết quả hoàn tiền.')+'<section class="surface">'+returnCards(await api('/support/returns'),'support')+'</section>';
  }
  async function operatorPage() {
    const [models,indexes,refunds,outbox,audit]=await Promise.all([api('/operator/segments'),api('/operator/indexes'),api('/operator/refunds'),api('/operator/outbox'),api('/operator/audit')]);
    return heading('Vận hành hệ thống.','Theo dõi mô hình, chỉ mục, đối soát và nhật ký.')+'<section id="segment-model-section" class="surface"><h2>Phân cụm khách hàng DBSCAN</h2><form id="train-segments-form"><div class="form-grid"><label class="field">eps<input name="eps" type="number" min="0.01" max="20" step="0.01" value="1.5" required></label><label class="field">min_samples<input name="min_samples" type="number" min="2" max="100" value="3" required></label><label class="field">Mốc huấn luyện (giờ địa phương)<input name="cutoff_at" type="datetime-local" required></label></div><p class="fine-print">Cần lịch sử đơn đã giao, sự đồng ý của khách và dữ liệu holdout sau mốc huấn luyện.</p><button class="button secondary" type="submit">Huấn luyện bản nháp</button><p class="form-error" role="alert"></p></form>'+models.map(m=>'<article class="operation-row"><strong>'+esc(m.model_version)+'</strong><p>'+esc(m.validation_state)+' · eps '+m.eps+' · min_samples '+m.min_samples+'</p><pre>'+esc(JSON.stringify(JSON.parse(m.metrics),null,2))+'</pre>'+(m.validation_state==='draft'?reportButton('Kiểm tra và áp dụng','approve-model',m.model_version):'')+'</article>').join('')+'</section><section id="search-index-section" class="surface"><h2>Chỉ mục tìm kiếm</h2><p>BGE-M3 chỉ dùng cho văn bản. Ảnh dùng visual encoder riêng.</p>'+reportButton('Xây chỉ mục văn bản','build-index','text')+' '+reportButton('Xây chỉ mục ảnh','build-index','image')+indexes.map(i=>'<p>'+esc(i.index_kind)+' · '+esc(i.model_revision)+' · '+esc(i.status)+'</p>').join('')+'</section><section id="refund-reconciliation-section" class="surface"><h2>Đối soát hoàn tiền</h2>'+refunds.map(r=>'<article class="operation-row"><strong>'+esc(r.id)+'</strong><p>'+money(r.amount)+' · '+esc(r.status)+'</p>'+(r.status==='pending'?reportButton('Mô phỏng xác nhận hoàn tiền','settle-refund',r.id):'')+'</article>').join('')+'</section><section id="expiry-section" class="surface"><h2>Hết hạn giữ chỗ</h2>'+reportButton('Xử lý giữ chỗ đã hết hạn','expire','')+'</section><section id="notification-section" class="surface"><h2>Thông báo chờ gửi</h2><button type="button" class="button secondary" data-report="dispatch-outbox">Gửi các sự kiện đến hạn</button><p>Các sự kiện được lưu bền vững. Cấu hình nhà cung cấp thông báo trước khi gửi.</p>'+outbox.slice(0,20).map(e=>'<p>'+esc(e.kind)+' · '+esc(e.status)+' · '+esc(e.aggregate_id)+'</p>').join('')+'</section><section id="audit-section" class="surface"><h2>Nhật ký thao tác</h2>'+audit.slice(0,30).map(e=>'<p>'+esc(e.created_at)+' · '+esc(e.action)+' · '+esc(e.reason)+'</p>').join('')+'</section>';
  }
  document.addEventListener('click',async event=>{
    const target=event.target.closest('[data-report]');
    if(!target)return;
    const {report,id}=target.dataset;
    target.disabled=true;
    try {
      if(report==='cancel-order')await cancelOrder(id);
      else if(report==='return-order')await returnOrder(id);
      else if(report==='image-search')imageSearch();
      else if(report==='ship')open('Giao hàng','<form id="ship-form" data-id="'+esc(id)+'"><label class="field">Đơn vị vận chuyển<input name="provider" minlength="2" maxlength="100" required></label><label class="field">Mã vận đơn<input name="tracking_code" minlength="3" maxlength="100" required></label><button class="button primary" type="submit">Xuất kho và giao hàng</button><p class="form-error" role="alert"></p></form>');
      else if(report==='review-return')open('Xét duyệt đổi trả','<form id="review-return-form" data-id="'+esc(id)+'"><label class="field">Quyết định<select name="decision"><option value="approve">Phê duyệt</option><option value="reject">Từ chối</option></select></label><label class="field">Lý do<textarea name="reason" minlength="5" maxlength="1000" required></textarea></label><button class="button primary" type="submit">Lưu quyết định</button><p class="form-error" role="alert"></p></form>');
      else if(report==='inspect-return')open('Kiểm tra hàng trả','<form id="inspect-return-form" data-id="'+esc(id)+'"><label class="field">Kết quả<select name="accepted"><option value="true">Đạt kiểm tra</option><option value="false">Không đạt</option></select></label><label class="field">Nhập kho bán lại<select name="restock"><option value="false">Không</option><option value="true">Có, hàng đủ điều kiện</option></select></label><label class="field">Ghi chú<textarea name="reason" minlength="5" maxlength="1000" required></textarea></label><button class="button primary" type="submit">Lưu kiểm tra</button><p class="form-error" role="alert"></p></form>');
      else {
        if(report==='refund-return')await api('/support/returns/'+id+'/refund',json('POST',{idempotency_key:'return-'+id}));
        else if(report==='settle-refund')await api('/operator/refunds/'+id+'/demo-settle',json('POST',{}));
        else if(report==='approve-model')await api('/operator/segments/'+id+'/approve',json('POST',{}));
        else if(report==='build-index')await api('/operator/indexes/build',json('POST',{kind:id}));
        else if(report==='dispatch-outbox')await api('/operator/outbox/dispatch',json('POST',{}));
        else if(report==='expire')await api('/operator/reservations/expire',json('POST',{}));
        else if(report==='delete-address')await api('/addresses/'+id,{method:'DELETE'});
        await refresh();toast('Đã cập nhật');
      }
    } catch(error){toast(error.message);}finally{target.disabled=false;}
  });
  document.addEventListener('submit',async event=>{
    const form=event.target;
    if(!form.matches('#cancel-order-form,#return-order-form,#image-search-form,#recommendation-consent-form,#address-form,#ship-form,#review-return-form,#inspect-return-form,#train-segments-form,.report-status-form,.report-stock-form,.report-product-form'))return;
    event.preventDefault();
    const data=Object.fromEntries(new FormData(form));
    const submit=event.submitter;
    const error=form.querySelector('[role="alert"]');
    if(error)error.textContent='';
    if(submit)submit.disabled=true;
    try {
      if(form.id==='image-search-form'){
        const file=form.querySelector('input[type="file"]').files[0];
        if(!file||file.size>5*1024*1024)throw new Error('Chọn ảnh tối đa 5 MB.');
        const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('Không đọc được tệp ảnh.'));reader.readAsDataURL(file);});
        const result=await api('/search',json('POST',{query:String(data.query),image_base64:encoded,media_consent:data.consent==='on'}));
        document.querySelector('#image-search-results').innerHTML='<h3>Kết quả tìm kiếm</h3>'+productGrid(getProducts().filter(p=>result.product_ids.includes(p.id)));
        return;
      }
      if(form.id==='cancel-order-form')await api('/orders/'+form.dataset.id+'/cancel',json('POST',{reason:data.reason}));
      else if(form.id==='return-order-form')await api('/orders/'+form.dataset.id+'/returns',json('POST',{reason:data.reason,evidence:data.evidence,lines:Object.entries(data).filter(([key,value])=>key.startsWith('line:')&&Number(value)>0).map(([key,value])=>({order_line_id:key.slice(5),quantity:Number(value)}))}));
      else if(form.id==='recommendation-consent-form')await api('/me/recommendation-consent',json('PUT',{consent:data.consent==='on'}));
      else if(form.id==='address-form')await api('/addresses',json('POST',data));
      else if(form.id==='ship-form')await api('/admin/orders/'+form.dataset.id+'/ship',json('POST',data));
      else if(form.id==='review-return-form')await api('/support/returns/'+form.dataset.id,json('PATCH',data));
      else if(form.id==='inspect-return-form')await api('/admin/returns/'+form.dataset.id+'/inspect',json('POST',{...data,accepted:data.accepted==='true',restock:data.restock==='true'}));
      else if(form.id==='train-segments-form')await api('/operator/segments/train',json('POST',{eps:Number(data.eps),min_samples:Number(data.min_samples),cutoff_at:new Date(data.cutoff_at).toISOString()}));
      else if(form.matches('.report-status-form'))await api('/admin/orders/'+form.dataset.id,json('PATCH',data));
      else if(form.matches('.report-stock-form'))await api('/admin/variants/'+encodeURIComponent(form.dataset.id),json('PATCH',{stock:Number(data.stock)}));
      else if(form.matches('.report-product-form'))await api('/admin/products/'+encodeURIComponent(form.dataset.id),json('PATCH',{...data,price:Number(data.price),active:data.active==='true'}));
      if(modal.open)modal.close();
      await refresh();toast('Đã cập nhật');
    }catch(err){if(error)error.textContent=err.message;else toast(err.message);}finally{if(submit)submit.disabled=false;}
  });
  return {recommendationsPage,addressesPage,staffPage};
}
